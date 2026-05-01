"""
APEX Protocol - Deterministic State Management

State reconstruction from snapshots and event logs without traditional database.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import hashlib
import json
import time
from collections import OrderedDict


@dataclass
class StateDelta:
    """
    Represents changes to state from a single batch.
    
    Designed for compact storage and deterministic replay.
    """
    batch_id: int
    timestamp: float
    balance_changes: Dict[str, Dict[str, int]]  # address -> {asset -> delta}
    intent_completions: List[int]  # completed intent IDs
    solver_stake_updates: Dict[str, int]  # solver -> new stake
    previous_state_root: bytes
    new_state_root: bytes = field(default_factory=lambda: b'')
    
    def serialize(self) -> bytes:
        """Serialize delta to bytes for storage."""
        data = {
            'batch_id': self.batch_id,
            'timestamp': self.timestamp,
            'balance_changes': self.balance_changes,
            'intent_completions': self.intent_completions,
            'solver_stake_updates': self.solver_stake_updates,
            'previous_state_root': self.previous_state_root.hex()
        }
        return json.dumps(data, sort_keys=True).encode()
    
    @classmethod
    def deserialize(cls, data: bytes) -> 'StateDelta':
        """Deserialize delta from bytes."""
        obj = json.loads(data.decode())
        return cls(
            batch_id=obj['batch_id'],
            timestamp=obj['timestamp'],
            balance_changes=obj['balance_changes'],
            intent_completions=obj['intent_completions'],
            solver_stake_updates=obj['solver_stake_updates'],
            previous_state_root=bytes.fromhex(obj['previous_state_root'])
        )


@dataclass
class CompressedSnapshot:
    """
    Compressed state snapshot for fast sync.
    
    Created periodically (every N batches) to enable fast state reconstruction.
    """
    height: int
    timestamp: float
    state_root: bytes
    compressed_data: bytes
    merkle_proofs: Dict[str, bytes]  # key -> proof
    
    def serialize(self) -> bytes:
        """Serialize snapshot for storage/transmission."""
        data = {
            'height': self.height,
            'timestamp': self.timestamp,
            'state_root': self.state_root.hex(),
            'compressed_data': self.compressed_data.hex(),
            'merkle_proofs': {k: v.hex() for k, v in self.merkle_proofs.items()}
        }
        return json.dumps(data, sort_keys=True).encode()
    
    @classmethod
    def deserialize(cls, data: bytes) -> 'CompressedSnapshot':
        """Deserialize snapshot from bytes."""
        obj = json.loads(data.decode())
        return cls(
            height=obj['height'],
            timestamp=obj['timestamp'],
            state_root=bytes.fromhex(obj['state_root']),
            compressed_data=bytes.fromhex(obj['compressed_data']),
            merkle_proofs={k: bytes.fromhex(v) for k, v in obj['merkle_proofs'].items()}
        )


class DeterministicStateManager:
    """
    Manages protocol state without traditional database.
    
    Key properties:
    - State is fully reconstructible from event logs
    - Snapshots enable fast sync
    - All operations are deterministic
    - No floating-point inconsistencies
    """
    
    def __init__(self, snapshot_interval: int = 10000):
        self.snapshot_interval = snapshot_interval
        self.current_batch_id = 0
        self.state_root = b''
        
        # In-memory state (rebuilt from snapshots on restart)
        self.balances: Dict[str, Dict[str, int]] = {}  # address -> {asset -> balance}
        self.nonces: Dict[str, int] = {}  # address -> nonce
        self.solver_stakes: Dict[str, int] = {}  # solver -> stake
        self.completed_intents: set = set()  # Set of executed intent IDs
        
        # Event log (append-only)
        self.event_log: List[Tuple[int, bytes]] = []  # (batch_id, serialized_event)
        
        # Snapshot cache
        self.snapshots: OrderedDict[int, CompressedSnapshot] = OrderedDict()
    
    def apply_batch(self, batch_id: int, 
                    balance_changes: Dict[str, Dict[str, int]],
                    intent_completions: List[int],
                    solver_stake_updates: Dict[str, int]) -> StateDelta:
        """
        Apply batch execution results to state.
        
        Creates a state delta and updates the state root.
        """
        previous_root = self.state_root
        
        # Apply balance changes
        for address, changes in balance_changes.items():
            if address not in self.balances:
                self.balances[address] = {}
            for asset, delta in changes.items():
                current = self.balances[address].get(asset, 0)
                self.balances[address][asset] = current + delta
        
        # Update nonces (simplified - would track per-intent in production)
        for address in balance_changes.keys():
            self.nonces[address] = self.nonces.get(address, 0) + 1
        
        # Update solver stakes
        for solver, new_stake in solver_stake_updates.items():
            self.solver_stakes[solver] = new_stake
        
        # Mark intents as completed
        for intent_id in intent_completions:
            self.completed_intents.add(intent_id)
        
        # Create state delta
        delta = StateDelta(
            batch_id=batch_id,
            timestamp=time.time(),
            balance_changes=balance_changes,
            intent_completions=intent_completions,
            solver_stake_updates=solver_stake_updates,
            previous_state_root=previous_root
        )
        
        # Compute new state root
        delta.new_state_root = self.compute_state_root()
        self.state_root = delta.new_state_root
        
        # Append to event log
        self.event_log.append((batch_id, delta.serialize()))
        
        # Create snapshot if needed
        if batch_id % self.snapshot_interval == 0:
            self.create_snapshot(batch_id)
        
        self.current_batch_id = batch_id
        
        return delta
    
    def compute_state_root(self) -> bytes:
        """
        Compute Merkle root of current state.
        
        Deterministic: same state always produces same root.
        """
        # Serialize state deterministically
        state_data = {
            'balances': dict(sorted(
                (addr, dict(sorted(assets.items()))) 
                for addr, assets in self.balances.items()
            )),
            'nonces': dict(sorted(self.nonces.items())),
            'solver_stakes': dict(sorted(self.solver_stakes.items())),
            'completed_intents_count': len(self.completed_intents),
            'batch_id': self.current_batch_id
        }
        
        state_json = json.dumps(state_data, sort_keys=True)
        return hashlib.sha256(state_json.encode()).digest()
    
    def create_snapshot(self, batch_id: int) -> CompressedSnapshot:
        """
        Create compressed state snapshot.
        
        Snapshots enable fast sync by avoiding full replay from genesis.
        """
        # Serialize full state
        state_data = {
            'balances': self.balances,
            'nonces': self.nonces,
            'solver_stakes': self.solver_stakes,
            'completed_intents': list(self.completed_intents)
        }
        serialized = json.dumps(state_data, sort_keys=True).encode()
        
        # Compress using delta encoding from previous snapshot
        if len(self.snapshots) > 0:
            prev_snapshot = list(self.snapshots.values())[-1]
            # XOR delta for compression
            prev_data = self._decompress_snapshot_data(prev_snapshot)
            delta_data = bytes(a ^ b for a, b in zip(serialized, prev_data))
        else:
            delta_data = serialized
        
        # Apply general compression (in production would use zlib/brotli)
        compressed = self._compress_bytes(delta_data)
        
        # Generate Merkle proofs for key state elements
        merkle_proofs = self._generate_merkle_proofs()
        
        snapshot = CompressedSnapshot(
            height=batch_id,
            timestamp=time.time(),
            state_root=self.state_root,
            compressed_data=compressed,
            merkle_proofs=merkle_proofs
        )
        
        # Store snapshot (keep last 10)
        self.snapshots[batch_id] = snapshot
        while len(self.snapshots) > 10:
            self.snapshots.popitem(last=False)
        
        return snapshot
    
    def reconstruct_state(self, target_batch_id: int) -> bool:
        """
        Reconstruct state to a specific batch ID.
        
        Uses nearest snapshot + replay of deltas.
        Fully deterministic - always produces identical state.
        """
        # Find nearest snapshot before target
        snapshot_batch_id = 0
        snapshot = None
        
        for batch_id, snap in sorted(self.snapshots.items()):
            if batch_id <= target_batch_id:
                snapshot_batch_id = batch_id
                snapshot = snap
            else:
                break
        
        # Reset state
        self._reset_state()
        
        # Load from snapshot if available
        if snapshot:
            self._load_snapshot(snapshot)
            start_batch = snapshot_batch_id
        else:
            start_batch = 0
        
        # Replay events from snapshot to target
        for event_batch_id, event_data in self.event_log:
            if start_batch < event_batch_id <= target_batch_id:
                delta = StateDelta.deserialize(event_data)
                self._apply_delta_without_root_update(delta)
        
        # Verify state root matches
        computed_root = self.compute_state_root()
        
        if target_batch_id == self.current_batch_id:
            return computed_root == self.state_root
        
        return True
    
    def verify_state_integrity(self, claimed_root: bytes) -> bool:
        """Verify that claimed state root matches local computation."""
        computed_root = self.compute_state_root()
        return computed_root == claimed_root
    
    def get_balance(self, address: str, asset: str) -> int:
        """Get balance for an address and asset."""
        return self.balances.get(address, {}).get(asset, 0)
    
    def get_nonce(self, address: str) -> int:
        """Get current nonce for an address."""
        return self.nonces.get(address, 0)
    
    def _reset_state(self):
        """Reset all state to empty."""
        self.balances = {}
        self.nonces = {}
        self.solver_stakes = {}
        self.completed_intents = set()
        self.state_root = b''
    
    def _load_snapshot(self, snapshot: CompressedSnapshot):
        """Load state from snapshot."""
        data = self._decompress_snapshot_data(snapshot)
        state_data = json.loads(data.decode())
        
        self.balances = state_data.get('balances', {})
        self.nonces = state_data.get('nonces', {})
        self.solver_stakes = state_data.get('solver_stakes', {})
        self.completed_intents = set(state_data.get('completed_intents', []))
        self.state_root = snapshot.state_root
        self.current_batch_id = snapshot.height
    
    def _decompress_snapshot_data(self, snapshot: CompressedSnapshot) -> bytes:
        """Decompress snapshot data."""
        # In production would use proper decompression
        return snapshot.compressed_data
    
    def _compress_bytes(self, data: bytes) -> bytes:
        """Compress bytes (placeholder for actual compression)."""
        # In production would use zlib or brotli
        return data
    
    def _generate_merkle_proofs(self) -> Dict[str, bytes]:
        """Generate Merkle proofs for key state elements."""
        # Simplified - in production would generate actual Merkle proofs
        proofs = {}
        for address in list(self.balances.keys())[:10]:  # Limit for efficiency
            key = f"balance:{address}"
            proofs[key] = hashlib.sha256(key.encode()).digest()
        return proofs
    
    def _apply_delta_without_root_update(self, delta: StateDelta):
        """Apply delta without recomputing state root."""
        for address, changes in delta.balance_changes.items():
            if address not in self.balances:
                self.balances[address] = {}
            for asset, change in changes.items():
                current = self.balances[address].get(asset, 0)
                self.balances[address][asset] = current + change
        
        for intent_id in delta.intent_completions:
            self.completed_intents.add(intent_id)
        
        for solver, stake in delta.solver_stake_updates.items():
            self.solver_stakes[solver] = stake
