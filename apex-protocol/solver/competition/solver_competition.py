"""
APEX Protocol - Solver Competition Module

Solver bidding and selection mechanism for batch execution.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import math
import time

from ...core.intent.intent import TradingIntent, IntentCommitment
from ...core.batch.auction import Batch, ClearingResult, Execution


@dataclass
class SolverBid:
    """
    A solver's bid to execute a batch.
    
    Includes price improvement commitments and performance bond.
    """
    solver: str  # Solver address
    batch_id: int
    intent_commitments: List[IntentCommitment]
    clearing_prices: Dict[tuple, float]  # asset_pair -> committed price
    signature: str
    performance_bond: int  # Slashing collateral
    timestamp: float = field(default_factory=time.time)
    
    def hash(self) -> bytes:
        """Compute deterministic hash of the bid."""
        import hashlib
        commitments_hash = b''.join(
            f"{c.intent_id}:{c.executed_amount}:{c.execution_price}:{c.route}".encode()
            for c in self.intent_commitments
        )
        prices_hash = str(sorted(self.clearing_prices.items())).encode()
        data = f"{self.solver}:{self.batch_id}:{self.performance_bond}:{self.timestamp}".encode()
        return hashlib.sha256(data + commitments_hash + prices_hash).digest()


@dataclass
class SolverAuction:
    """Represents an auction for batch execution rights."""
    batch_id: int
    bid_deadline: float
    minimum_solvers: int
    bids: List[SolverBid] = field(default_factory=list)
    winner: Optional[str] = None
    status: str = "OPEN"  # OPEN, CLOSED, FINALIZED
    
    def add_bid(self, bid: SolverBid):
        """Add a bid to the auction if before deadline."""
        if time.time() > self.bid_deadline:
            raise ValueError("Auction deadline passed")
        if bid.batch_id != self.batch_id:
            raise ValueError(f"Invalid batch_id: {bid.batch_id} != {self.batch_id}")
        self.bids.append(bid)
    
    def close(self):
        """Close the auction to new bids."""
        self.status = "CLOSED"


@dataclass
class SolverPerformance:
    """Tracks historical performance of a solver."""
    solver: str
    total_batches: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    total_slashed: int = 0
    avg_price_improvement: float = 0.0
    last_active: float = 0.0
    
    @property
    def success_rate(self) -> float:
        if self.total_batches == 0:
            return 0.5
        return self.successful_executions / self.total_batches
    
    @property
    def reputation_score(self) -> float:
        """Calculate composite reputation score."""
        base_score = self.success_rate
        activity_bonus = min(0.1, math.log(max(1, self.total_batches)) * 0.01)
        recency = time.time() - self.last_active
        recency_penalty = min(0.2, recency / 86400)  # Decay over days
        
        return max(0.0, min(1.0, base_score + activity_bonus - recency_penalty))


class SolverCompetition:
    """
    Manages solver competition for batch execution rights.
    
    Implements anti-cartel mechanisms and fair selection.
    """
    
    def __init__(self, min_solvers: int = 3, challenge_window: int = 300):
        self.min_solvers = min_solvers
        self.challenge_window = challenge_window  # seconds
        self.solver_performance: Dict[str, SolverPerformance] = {}
        self.solver_stakes: Dict[str, int] = {}  # solver -> total stake
        self.auctions: Dict[int, SolverAuction] = {}
        self.price_improvement_history: List[float] = []
        self.cartel_detection_enabled = True
    
    def request_solver_bids(self, batch: Batch) -> SolverAuction:
        """
        Create auction for batch execution.
        
        In production, this would broadcast to P2P network.
        """
        auction = SolverAuction(
            batch_id=batch.batch_id,
            bid_deadline=batch.creation_time + self.challenge_window,
            minimum_solvers=self.min_solvers
        )
        self.auctions[batch.batch_id] = auction
        return auction
    
    def submit_bid(self, bid: SolverBid) -> bool:
        """Submit a solver bid to the appropriate auction."""
        if bid.batch_id not in self.auctions:
            return False
        
        auction = self.auctions[bid.batch_id]
        
        try:
            auction.add_bid(bid)
            
            # Initialize solver performance tracking if needed
            if bid.solver not in self.solver_performance:
                self.solver_performance[bid.solver] = SolverPerformance(solver=bid.solver)
            
            return True
        except ValueError:
            return False
    
    def select_winning_bid(self, batch_id: int) -> Optional[SolverBid]:
        """
        Select winning solver bid using deterministic scoring.
        
        Scoring factors:
        1. Price improvement (60% weight)
        2. Stake amount (30% weight)
        3. Historical performance (10% weight)
        
        Anti-monopoly: rotates among top bidders within threshold.
        """
        if batch_id not in self.auctions:
            return None
        
        auction = self.auctions[batch_id]
        
        if len(auction.bids) == 0:
            return None
        
        # Check for cartel behavior
        if self.cartel_detection_enabled:
            if self._detect_cartel_behavior(auction.bids):
                self._handle_cartel_detection(auction)
        
        # Score each bid
        scored_bids = []
        for bid in auction.bids:
            price_improvement = self._calculate_price_improvement(bid, batch_id)
            stake_score = math.log(max(1, bid.performance_bond))
            historical_score = self._get_historical_performance(bid.solver)
            
            # Weighted scoring (deterministic)
            total_score = (
                0.6 * price_improvement +
                0.3 * stake_score +
                0.1 * historical_score
            )
            
            scored_bids.append((total_score, bid))
        
        # Sort by score descending, then by solver address (deterministic tie-break)
        scored_bids.sort(key=lambda x: (-x[0], x[1].solver))
        
        # Anti-monopoly: rotate among top bidders if scores are within threshold
        top_score = scored_bids[0][0]
        eligible_bids = [
            bid for score, bid in scored_bids
            if score >= top_score * 0.95  # Within 5% of best
        ]
        
        # Deterministic rotation based on batch_id
        winner_idx = batch_id % len(eligible_bids)
        winner = eligible_bids[winner_idx]
        
        # Update auction
        auction.winner = winner.solver
        auction.status = "FINALIZED"
        
        # Record price improvement for analysis
        improvement = self._calculate_price_improvement(winner, batch_id)
        self.price_improvement_history.append(improvement)
        
        return winner
    
    def _calculate_price_improvement(self, bid: SolverBid, batch_id: int) -> float:
        """
        Calculate aggregate price improvement vs baseline clearing prices.
        
        Higher improvement = better score.
        """
        # Get baseline prices from batch auction result
        # In production, would compare to actual clearing prices
        total_improvement = 0.0
        
        for commitment in bid.intent_commitments:
            # Baseline is typically 1.0 (no improvement)
            # Commitments < 1.0 for buys (better price), > 1.0 for sells
            baseline_price = 1.0
            if commitment.execution_price != 0:
                improvement = abs(commitment.execution_price - baseline_price) / baseline_price
                total_improvement += improvement * commitment.executed_amount
        
        # Normalize by total volume
        total_volume = sum(c.executed_amount for c in bid.intent_commitments)
        if total_volume > 0:
            return total_improvement / total_volume
        return 0.0
    
    def _get_historical_performance(self, solver: str) -> float:
        """Get historical performance score for a solver."""
        if solver not in self.solver_performance:
            return 0.5  # Default for new solvers
        
        perf = self.solver_performance[solver]
        return perf.reputation_score
    
    def _detect_cartel_behavior(self, bids: List[SolverBid]) -> bool:
        """
        Detect potential cartel behavior through statistical analysis.
        
        Indicators:
        1. Abnormally low price improvement variance
        2. High correlation in bidding patterns
        3. Consistent rotation among same solvers
        """
        if len(bids) < 3:
            return False
        
        # Check price improvement variance
        improvements = [self._calculate_price_improvement(bid, bid.batch_id) for bid in bids]
        
        if len(improvements) < 2:
            return False
        
        mean_improvement = sum(improvements) / len(improvements)
        variance = sum((x - mean_improvement) ** 2 for x in improvements) / len(improvements)
        
        # If variance is too low, potential collusion
        if variance < 0.0001:  # Threshold tuned empirically
            return True
        
        # Additional checks could be added here:
        # - Bid timing correlation
        # - Price level correlation
        # - Winner rotation patterns
        
        return False
    
    def _handle_cartel_detection(self, auction: SolverAuction):
        """
        Handle detected cartel behavior.
        
        Mitigations:
        1. Emit alert for monitoring
        2. Adjust scoring to favor underrepresented solvers
        3. Consider emergency RFQ mode
        """
        # Log detection (in production would emit event)
        print(f"CARTEL DETECTED in auction {auction.batch_id}")
        
        # Could implement additional mitigations here
        pass
    
    def update_solver_performance(self, solver: str, success: bool, 
                                  slashed_amount: int = 0,
                                  price_improvement: float = 0.0):
        """Update solver performance metrics after execution."""
        if solver not in self.solver_performance:
            self.solver_performance[solver] = SolverPerformance(solver=solver)
        
        perf = self.solver_performance[solver]
        perf.total_batches += 1
        
        if success:
            perf.successful_executions += 1
        else:
            perf.failed_executions += 1
        
        perf.total_slashed += slashed_amount
        perf.last_active = time.time()
        
        # Update running average of price improvement
        n = perf.total_batches
        old_avg = perf.avg_price_improvement
        perf.avg_price_improvement = ((n - 1) * old_avg + price_improvement) / n
    
    def get_eligible_solvers(self, min_stake: int) -> List[str]:
        """Get list of solvers meeting minimum stake requirement."""
        eligible = []
        for solver, stake in self.solver_stakes.items():
            if stake >= min_stake:
                eligible.append(solver)
        return eligible
    
    def register_solver(self, solver: str, stake: int):
        """Register a new solver with stake."""
        self.solver_stakes[solver] = stake
        self.solver_performance[solver] = SolverPerformance(solver=solver)
    
    def slash_solver(self, solver: str, amount: int, reason: str):
        """Slash solver stake for misbehavior."""
        if solver not in self.solver_stakes:
            return
        
        actual_slash = min(amount, self.solver_stakes[solver])
        self.solver_stakes[solver] -= actual_slash
        
        # Update performance tracking
        if solver in self.solver_performance:
            self.solver_performance[solver].total_slashed += actual_slash
        
        # Log slashing event (in production would emit event)
        print(f"SOLVER SLASHED: {solver}, amount={actual_slash}, reason={reason}")
