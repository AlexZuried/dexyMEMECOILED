"""
APEX Protocol - Batch Auction Engine

Deterministic batch auction implementation for fair order matching.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import time

from ..intent.intent import TradingIntent, IntentCommitment, ActionType


@dataclass
class Batch:
    """
    A collection of intents to be executed together.
    
    Batches are created at deterministic intervals (e.g., 200ms)
    and processed through the batch auction mechanism.
    """
    batch_id: int
    intents: List[TradingIntent]
    creation_time: float
    state_root: bytes  # Merkle root of state before batch
    
    def __post_init__(self):
        """Ensure intents are sorted deterministically."""
        # Sort by: stake (desc), timestamp (asc), hash (asc)
        self.intents.sort(
            key=lambda i: (-i.stake_deposit, i.deadline, i.hash())
        )
    
    def hash(self) -> bytes:
        """Compute deterministic hash of the batch."""
        import hashlib
        intent_hashes = b''.join(i.hash() for i in self.intents)
        data = f"{self.batch_id}:{self.creation_time}:{self.state_root.hex()}".encode()
        return hashlib.sha256(data + intent_hashes).digest()


@dataclass
class Execution:
    """Represents a single intent execution."""
    intent_id: int
    trader: str
    asset_pair: tuple
    action: ActionType
    executed_amount: int
    execution_price: float
    route: str
    timestamp: float


@dataclass
class ClearingResult:
    """Result of batch clearing computation."""
    batch_id: int
    executions: List[Execution]
    clearing_prices: Dict[tuple, float]  # asset_pair -> price
    unmatched_intents: List[int]  # intent_ids that couldn't be matched
    total_volume: int
    state_delta: bytes  # Encoded state changes


class BatchAuctionEngine:
    """
    Deterministic batch auction engine.
    
    Implements uniform price clearing to maximize executed volume
    while maintaining price consistency across all participants.
    """
    
    def __init__(self, batch_window_ms: int = 200):
        self.batch_window = batch_window_ms / 1000.0  # Convert to seconds
        self.pending_intents: List[TradingIntent] = []
        self.current_batch_id = 0
        self.last_batch_time = 0.0
        self.price_history: Dict[tuple, List[Tuple[float, float]]] = defaultdict(list)  # pair -> [(time, price)]
    
    def collect_intents(self, current_time: float) -> Optional[Batch]:
        """
        Collect intents into deterministic batches.
        
        Uses time-window batching with deterministic ordering.
        Returns a batch if the window has closed and there are intents.
        """
        # Wait for batch window to close
        if current_time - self.last_batch_time < self.batch_window:
            return None
        
        if not self.pending_intents:
            self.last_batch_time = current_time
            return None
        
        # Create batch (intents already sorted in Batch.__post_init__)
        batch = Batch(
            batch_id=self.current_batch_id,
            intents=self.pending_intents.copy(),
            creation_time=self.last_batch_time,
            state_root=self._get_current_state_root()
        )
        
        # Reset for next batch
        self.current_batch_id += 1
        self.pending_intents = []
        self.last_batch_time = current_time
        
        return batch
    
    def add_intent(self, intent: TradingIntent):
        """Add an intent to the pending pool."""
        self.pending_intents.append(intent)
    
    def compute_clearing_prices(self, batch: Batch) -> ClearingResult:
        """
        Compute uniform clearing prices using batch auction mechanism.
        
        Maximizes executed volume while maintaining price consistency.
        All matched orders execute at the same clearing price per pair.
        """
        # Group intents by asset pair
        pair_books: Dict[tuple, Dict[str, List]] = defaultdict(
            lambda: {'buys': [], 'sells': []}
        )
        
        for intent in batch.intents:
            book = pair_books[intent.asset_pair]
            if intent.action == ActionType.BUY:
                # Max price trader willing to pay
                max_price = intent.amount_in / intent.min_amount_out
                book['buys'].append((max_price, intent))
            else:
                # Min price trader willing to accept
                min_price = intent.min_amount_out / intent.amount_in
                book['sells'].append((min_price, intent))
        
        clearing_prices = {}
        executions = []
        unmatched_intents = []
        total_volume = 0
        
        for pair, book in pair_books.items():
            # Sort buys descending, sells ascending
            book['buys'].sort(key=lambda x: -x[0])
            book['sells'].sort(key=lambda x: x[0])
            
            # Find clearing price where supply meets demand
            clearing_price = self._find_clearing_price(book['buys'], book['sells'])
            
            if clearing_price is None:
                # No crossing point - all intents unmatched
                for _, intent in book['buys']:
                    unmatched_intents.append(intent.intent_id)
                for _, intent in book['sells']:
                    unmatched_intents.append(intent.intent_id)
                continue
            
            clearing_prices[pair] = clearing_price
            
            # Generate executions at uniform price
            cumulative_buy = 0
            cumulative_sell = 0
            
            # Process buys
            for buy_price, buy_intent in book['buys']:
                if buy_price >= clearing_price:
                    exec_amount = min(
                        buy_intent.amount_in,
                        buy_intent.min_amount_out * clearing_price
                    )
                    executions.append(Execution(
                        intent_id=buy_intent.intent_id,
                        trader=buy_intent.trader,
                        asset_pair=buy_intent.asset_pair,
                        action=buy_intent.action,
                        executed_amount=int(exec_amount),
                        execution_price=clearing_price,
                        route='INTERNAL',
                        timestamp=batch.creation_time
                    ))
                    cumulative_buy += exec_amount
                    total_volume += exec_amount
                else:
                    unmatched_intents.append(buy_intent.intent_id)
            
            # Process sells
            for sell_price, sell_intent in book['sells']:
                if sell_price <= clearing_price:
                    exec_amount = min(
                        sell_intent.amount_in,
                        sell_intent.min_amount_out / clearing_price
                    )
                    executions.append(Execution(
                        intent_id=sell_intent.intent_id,
                        trader=sell_intent.trader,
                        asset_pair=sell_intent.asset_pair,
                        action=sell_intent.action,
                        executed_amount=int(exec_amount),
                        execution_price=clearing_price,
                        route='INTERNAL',
                        timestamp=batch.creation_time
                    ))
                    cumulative_sell += exec_amount
                    total_volume += exec_amount
                else:
                    unmatched_intents.append(sell_intent.intent_id)
            
            # Record price for history
            self.price_history[pair].append((batch.creation_time, clearing_price))
        
        # Compute state delta (simplified - in production would be full state diff)
        state_delta = self._compute_state_delta(executions)
        
        return ClearingResult(
            batch_id=batch.batch_id,
            executions=executions,
            clearing_prices=clearing_prices,
            unmatched_intents=unmatched_intents,
            total_volume=total_volume,
            state_delta=state_delta
        )
    
    def _find_clearing_price(self, buys: List[Tuple[float, TradingIntent]], 
                             sells: List[Tuple[float, TradingIntent]]) -> Optional[float]:
        """
        Find single clearing price that maximizes executed volume.
        
        Returns None if no crossing point exists (highest buy < lowest sell).
        """
        if not buys or not sells:
            return None
        
        # Check if highest buy >= lowest sell
        if buys[0][0] < sells[0][0]:
            return None  # No overlap
        
        # Build cumulative demand and supply curves
        cumulative_buy_volume = 0
        cumulative_sell_volume = 0
        
        buy_idx = 0
        sell_idx = 0
        
        # Find the crossing point
        while buy_idx < len(buys) and sell_idx < len(sells):
            buy_price, buy_intent = buys[buy_idx]
            sell_price, sell_intent = sells[sell_idx]
            
            if buy_price < sell_price:
                break
            
            # Add volume at this price level
            buy_vol = min(buy_intent.amount_in, buy_intent.min_amount_out * buy_price)
            sell_vol = min(sell_intent.amount_in, sell_intent.min_amount_out / sell_price)
            
            cumulative_buy_volume += buy_vol
            cumulative_sell_volume += sell_vol
            
            # Move to next order
            if cumulative_buy_volume > cumulative_sell_volume:
                sell_idx += 1
            else:
                buy_idx += 1
        
        # Return the price at the crossing point
        # Deterministic tie-breaking: use sell price (conservative)
        if sell_idx < len(sells):
            return sells[min(sell_idx, len(sells)-1)][0]
        elif buy_idx < len(buys):
            return buys[buy_idx][0]
        else:
            return sells[-1][0]
    
    def _compute_state_delta(self, executions: List[Execution]) -> bytes:
        """
        Compute state delta from executions.
        
        In production, this would generate a compact encoding of
        all balance changes for inclusion in the state tree.
        """
        import json
        delta = {
            'executions': len(executions),
            'volume': sum(e.executed_amount for e in executions),
            'timestamp': time.time()
        }
        return json.dumps(delta, sort_keys=True).encode()
    
    def _get_current_state_root(self) -> bytes:
        """
        Get current state root hash.
        
        In production, this would compute the Merkle root of the
        full application state.
        """
        import hashlib
        # Placeholder - in production would be actual state root
        state_data = f"batch:{self.current_batch_id}:pending:{len(self.pending_intents)}"
        return hashlib.sha256(state_data.encode()).digest()
    
    def get_last_price(self, asset_pair: tuple, window_seconds: float = 3600.0) -> Optional[float]:
        """Get the last clearing price for an asset pair within the time window."""
        current_time = time.time()
        prices = self.price_history.get(asset_pair, [])
        
        # Find most recent price within window
        for t, price in reversed(prices):
            if current_time - t <= window_seconds:
                return price
        
        return None
    
    def get_twap_price(self, asset_pair: tuple, window_seconds: float = 3600.0) -> Optional[float]:
        """Calculate time-weighted average price for an asset pair."""
        current_time = time.time()
        prices = self.price_history.get(asset_pair, [])
        
        if not prices:
            return None
        
        # Filter to window
        window_prices = [(t, p) for t, p in prices if current_time - t <= window_seconds]
        
        if not window_prices:
            return None
        
        # Simple TWAP (in production would weight by time intervals)
        return sum(p for _, p in window_prices) / len(window_prices)
