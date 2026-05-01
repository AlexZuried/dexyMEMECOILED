"""
APEX Protocol - Core Intent Module

Intent structures and validation for the APEX decentralized exchange.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
import hashlib
import time


class ActionType(Enum):
    """Type of trading action."""
    BUY = "BUY"
    SELL = "SELL"
    LIQUIDATE = "LIQUIDATE"


@dataclass
class TradingIntent:
    """
    A signed trading intent expressing what a trader wants to execute.
    
    Traders express *what* they want, not *how* to execute.
    Solvers compete to provide the best execution.
    """
    trader: str  # Address of the trader
    intent_id: int  # Unique per trader (nonce-based)
    action: ActionType
    asset_pair: tuple  # (base_asset, quote_asset)
    amount_in: int  # Amount to trade (in smallest units)
    min_amount_out: int  # Minimum output (limit protection)
    deadline: int  # Unix timestamp when intent expires
    stake_deposit: int  # Anti-spam stake deposit
    signature: str  # Cryptographic signature
    nonce: int = 0  # For replay prevention
    
    def __post_init__(self):
        """Validate intent after initialization."""
        if self.deadline < time.time():
            raise ValueError("Intent deadline has passed")
        if self.amount_in <= 0:
            raise ValueError("Amount must be positive")
        if self.min_amount_out <= 0:
            raise ValueError("Minimum output must be positive")
        if self.stake_deposit <= 0:
            raise ValueError("Stake deposit must be positive")
    
    def hash(self) -> bytes:
        """Compute deterministic hash of the intent."""
        data = f"{self.trader}:{self.intent_id}:{self.action.value}:{self.asset_pair}:{self.amount_in}:{self.min_amount_out}:{self.deadline}:{self.stake_deposit}:{self.nonce}"
        return hashlib.sha256(data.encode()).digest()
    
    def verify_signature(self, public_key: str) -> bool:
        """Verify the intent signature (placeholder for actual crypto)."""
        # In production: use ECDSA or EdDSA verification
        # This is a placeholder for the actual implementation
        return len(self.signature) > 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert intent to dictionary for serialization."""
        return {
            'trader': self.trader,
            'intent_id': self.intent_id,
            'action': self.action.value,
            'asset_pair': list(self.asset_pair),
            'amount_in': self.amount_in,
            'min_amount_out': self.min_amount_out,
            'deadline': self.deadline,
            'stake_deposit': self.stake_deposit,
            'signature': self.signature,
            'nonce': self.nonce
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TradingIntent':
        """Create intent from dictionary."""
        return cls(
            trader=data['trader'],
            intent_id=data['intent_id'],
            action=ActionType(data['action']),
            asset_pair=tuple(data['asset_pair']),
            amount_in=data['amount_in'],
            min_amount_out=data['min_amount_out'],
            deadline=data['deadline'],
            stake_deposit=data['stake_deposit'],
            signature=data['signature'],
            nonce=data.get('nonce', 0)
        )


@dataclass
class IntentCommitment:
    """
    Solver's commitment to execute a specific intent.
    
    Submitted as part of solver bids in the batch auction.
    """
    intent_id: int
    executed_amount: int
    execution_price: float  # Price at which execution will occur
    route: str  # Execution route: INTERNAL, EXTERNAL, CROSS_CHAIN
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'intent_id': self.intent_id,
            'executed_amount': self.executed_amount,
            'execution_price': self.execution_price,
            'route': self.route
        }


@dataclass
class IntentValidationResult:
    """Result of intent validation."""
    valid: bool
    error_message: Optional[str] = None
    required_stake: Optional[int] = None
    reputation_score: Optional[float] = None


class IntentValidator:
    """
    Validates trading intents before inclusion in batches.
    
    Implements stake-based spam prevention and reputation tracking.
    """
    
    def __init__(self, base_stake: int = 100):
        self.base_stake = base_stake
        self.trader_reputation: Dict[str, float] = {}  # trader -> reputation score
        self.processed_nonces: Dict[str, set] = {}  # trader -> set of used nonces
    
    def calculate_required_stake(self, trader: str, amount_in: int, 
                                  network_load: float = 0.5) -> int:
        """
        Calculate dynamic stake requirement based on:
        - Trader's historical validity rate (reputation)
        - Current network load
        - Intent size relative to market
        """
        base = self.base_stake
        
        # Reputation discount (good traders pay less)
        reputation = self.trader_reputation.get(trader, 0.5)
        reputation_discount = max(0.1, 1.0 - reputation * 0.5)
        
        # Network load multiplier
        load_multiplier = 1.0 + network_load * 2.0
        
        # Size-based adjustment (large orders need more stake)
        size_factor = min(amount_in / 1_000_000, 10.0)  # Cap at 10x
        size_multiplier = 1.0 + size_factor * 0.1
        
        required_stake = int(base * reputation_discount * load_multiplier * size_multiplier)
        return required_stake
    
    def validate_intent(self, intent: TradingIntent, 
                       current_time: float,
                       network_load: float = 0.5) -> IntentValidationResult:
        """
        Comprehensive intent validation.
        
        Checks:
        1. Signature validity
        2. Deadline not expired
        3. Stake sufficient
        4. No replay (nonce check)
        5. Amount constraints
        """
        # Check deadline
        if intent.deadline < current_time:
            return IntentValidationResult(
                valid=False,
                error_message="Intent deadline expired"
            )
        
        # Check for replay
        if intent.trader in self.processed_nonces:
            if intent.nonce in self.processed_nonces[intent.trader]:
                return IntentValidationResult(
                    valid=False,
                    error_message=f"Duplicate nonce: {intent.nonce}"
                )
        
        # Calculate and check stake
        required_stake = self.calculate_required_stake(
            intent.trader, 
            intent.amount_in,
            network_load
        )
        
        if intent.stake_deposit < required_stake:
            return IntentValidationResult(
                valid=False,
                error_message=f"Insufficient stake: {intent.stake_deposit} < {required_stake}",
                required_stake=required_stake
            )
        
        # Validate signature (placeholder)
        if not intent.signature or len(intent.signature) == 0:
            return IntentValidationResult(
                valid=False,
                error_message="Missing or invalid signature"
            )
        
        # All checks passed
        reputation = self.trader_reputation.get(intent.trader, 0.5)
        
        return IntentValidationResult(
            valid=True,
            required_stake=required_stake,
            reputation_score=reputation
        )
    
    def mark_intent_processed(self, intent: TradingIntent):
        """Mark an intent as processed to prevent replay."""
        if intent.trader not in self.processed_nonces:
            self.processed_nonces[intent.trader] = set()
        self.processed_nonces[intent.trader].add(intent.nonce)
        
        # Keep only last 1000 nonces per trader to prevent unbounded growth
        if len(self.processed_nonces[intent.trader]) > 1000:
            # Remove oldest nonces (assuming they're sorted)
            nonces = sorted(self.processed_nonces[intent.trader])
            self.processed_nonces[intent.trader] = set(nonces[-1000:])
    
    def update_reputation(self, trader: str, success: bool, severity: float = 1.0):
        """
        Update trader reputation based on execution outcome.
        
        Success increases reputation, failure decreases it.
        Severity affects the magnitude of change.
        """
        current_rep = self.trader_reputation.get(trader, 0.5)
        
        if success:
            # Increase reputation (diminishing returns near 1.0)
            delta = 0.01 * severity * (1.0 - current_rep)
            new_rep = min(1.0, current_rep + delta)
        else:
            # Decrease reputation (larger impact for severe failures)
            delta = 0.05 * severity * current_rep
            new_rep = max(0.0, current_rep - delta)
        
        self.trader_reputation[trader] = new_rep
    
    def get_reputation(self, trader: str) -> float:
        """Get current reputation score for a trader."""
        return self.trader_reputation.get(trader, 0.5)
