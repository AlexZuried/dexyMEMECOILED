"""
APEX Protocol - Test Suite

Tests for core protocol components.
"""

import unittest
import time
from typing import Dict, Any


class TestTradingIntent(unittest.TestCase):
    """Tests for TradingIntent class."""
    
    def setUp(self):
        from core.intent.intent import TradingIntent, ActionType
        
        self.TradingIntent = TradingIntent
        self.ActionType = ActionType
    
    def test_create_valid_intent(self):
        """Test creating a valid trading intent."""
        intent = self.TradingIntent(
            trader="0x1234567890abcdef",
            intent_id=1,
            action=self.ActionType.BUY,
            asset_pair=("ETH", "USDC"),
            amount_in=1000000000,  # 1 ETH in wei
            min_amount_out=2000000000,  # 2000 USDC
            deadline=int(time.time()) + 300,
            stake_deposit=100,
            signature="valid_signature_here",
            nonce=1
        )
        
        self.assertEqual(intent.trader, "0x1234567890abcdef")
        self.assertEqual(intent.action, self.ActionType.BUY)
        self.assertIsNotNone(intent.hash())
    
    def test_expired_intent(self):
        """Test that expired intents are rejected."""
        with self.assertRaises(ValueError):
            self.TradingIntent(
                trader="0x1234567890abcdef",
                intent_id=1,
                action=self.ActionType.BUY,
                asset_pair=("ETH", "USDC"),
                amount_in=1000000000,
                min_amount_out=2000000000,
                deadline=int(time.time()) - 100,  # Expired
                stake_deposit=100,
                signature="valid_signature"
            )
    
    def test_intent_hash_deterministic(self):
        """Test that intent hashing is deterministic."""
        future_deadline = int(time.time()) + 300
        intent1 = self.TradingIntent(
            trader="0x1234567890abcdef",
            intent_id=1,
            action=self.ActionType.BUY,
            asset_pair=("ETH", "USDC"),
            amount_in=1000000000,
            min_amount_out=2000000000,
            deadline=future_deadline,
            stake_deposit=100,
            signature="sig",
            nonce=1
        )
        
        intent2 = self.TradingIntent(
            trader="0x1234567890abcdef",
            intent_id=1,
            action=self.ActionType.BUY,
            asset_pair=("ETH", "USDC"),
            amount_in=1000000000,
            min_amount_out=2000000000,
            deadline=future_deadline,
            stake_deposit=100,
            signature="sig",
            nonce=1
        )
        
        self.assertEqual(intent1.hash(), intent2.hash())


class TestIntentValidator(unittest.TestCase):
    """Tests for IntentValidator class."""
    
    def setUp(self):
        from core.intent.intent import TradingIntent, ActionType, IntentValidator
        
        self.TradingIntent = TradingIntent
        self.ActionType = ActionType
        self.validator = IntentValidator(base_stake=100)
    
    def test_validate_valid_intent(self):
        """Test validation of a valid intent."""
        intent = self.TradingIntent(
            trader="0x1234567890abcdef",
            intent_id=1,
            action=self.ActionType.BUY,
            asset_pair=("ETH", "USDC"),
            amount_in=1000000000,
            min_amount_out=2000000000,
            deadline=int(time.time()) + 300,
            stake_deposit=500,  # High enough stake
            signature="valid_sig",
            nonce=1
        )
        
        result = self.validator.validate_intent(intent, time.time(), network_load=0.1)
        
        self.assertTrue(result.valid)
        self.assertIsNone(result.error_message)
    
    def test_replay_prevention(self):
        """Test that replayed intents are rejected."""
        intent = self.TradingIntent(
            trader="0x1234567890abcdef",
            intent_id=1,
            action=self.ActionType.BUY,
            asset_pair=("ETH", "USDC"),
            amount_in=1000000000,
            min_amount_out=2000000000,
            deadline=int(time.time()) + 300,
            stake_deposit=500,
            signature="valid_sig",
            nonce=1
        )
        
        # First validation should pass
        result1 = self.validator.validate_intent(intent, time.time(), network_load=0.1)
        self.assertTrue(result1.valid)
        
        # Mark as processed
        self.validator.mark_intent_processed(intent)
        
        # Second validation with same nonce should fail
        result2 = self.validator.validate_intent(intent, time.time(), network_load=0.1)
        self.assertFalse(result2.valid)
        self.assertIn("Duplicate nonce", result2.error_message)
    
    def test_insufficient_stake(self):
        """Test that intents with insufficient stake are rejected."""
        intent = self.TradingIntent(
            trader="0x1234567890abcdef",
            intent_id=1,
            action=self.ActionType.BUY,
            asset_pair=("ETH", "USDC"),
            amount_in=1000000000,
            min_amount_out=2000000000,
            deadline=int(time.time()) + 300,
            stake_deposit=10,  # Too low
            signature="valid_sig",
            nonce=1
        )
        
        result = self.validator.validate_intent(intent, time.time(), network_load=0.5)
        
        self.assertFalse(result.valid)
        self.assertIn("Insufficient stake", result.error_message)
        self.assertIsNotNone(result.required_stake)
    
    def test_reputation_updates(self):
        """Test reputation score updates."""
        trader = "0x1234567890abcdef"
        
        # Initial reputation should be 0.5
        initial_rep = self.validator.get_reputation(trader)
        self.assertEqual(initial_rep, 0.5)
        
        # Successful execution increases reputation
        self.validator.update_reputation(trader, success=True)
        rep_after_success = self.validator.get_reputation(trader)
        self.assertGreater(rep_after_success, initial_rep)
        
        # Failed execution decreases reputation
        self.validator.update_reputation(trader, success=False)
        rep_after_failure = self.validator.get_reputation(trader)
        self.assertLess(rep_after_failure, rep_after_success)


class TestBatchAuction(unittest.TestCase):
    """Tests for BatchAuctionEngine class."""
    
    def setUp(self):
        from core.batch.auction import BatchAuctionEngine, Batch
        from core.intent.intent import TradingIntent, ActionType
        
        self.engine = BatchAuctionEngine(batch_window_ms=200)
        self.TradingIntent = TradingIntent
        self.ActionType = ActionType
    
    def _create_intent(self, action: str, amount: int, min_out: int,
                       stake: int = 100, nonce: int = 1):
        """Helper to create test intents."""
        return self.TradingIntent(
            trader="0x1234567890abcdef",
            intent_id=nonce,
            action=self.ActionType.BUY if action == "BUY" else self.ActionType.SELL,
            asset_pair=("ETH", "USDC"),
            amount_in=amount,
            min_amount_out=min_out,
            deadline=int(time.time()) + 300,
            stake_deposit=stake,
            signature="valid_sig",
            nonce=nonce
        )
    
    def test_batch_creation(self):
        """Test batch creation from pending intents."""
        # Add intents
        intent1 = self._create_intent("BUY", 1000000000, 2000000000, nonce=1)
        intent2 = self._create_intent("SELL", 1000000000, 1800000000, nonce=2)
        
        self.engine.add_intent(intent1)
        self.engine.add_intent(intent2)
        
        # Collect batch (window closed)
        current_time = time.time()
        self.engine.last_batch_time = current_time - 1.0  # Force window close
        
        batch = self.engine.collect_intents(current_time)
        
        self.assertIsNotNone(batch)
        self.assertEqual(len(batch.intents), 2)
        self.assertEqual(batch.batch_id, 0)
    
    def test_clearing_price_computation(self):
        """Test clearing price computation with crossing orders."""
        # Create crossing buy and sell
        buy_intent = self._create_intent("BUY", 1000000000, 1800000000, nonce=1)
        sell_intent = self._create_intent("SELL", 1000000000, 1800000000, nonce=2)
        
        self.engine.add_intent(buy_intent)
        self.engine.add_intent(sell_intent)
        
        # Force batch creation
        current_time = time.time()
        self.engine.last_batch_time = current_time - 1.0
        
        batch = self.engine.collect_intents(current_time)
        result = self.engine.compute_clearing_prices(batch)
        
        self.assertGreater(len(result.executions), 0)
        self.assertGreater(result.total_volume, 0)
    
    def test_no_crossing_orders(self):
        """Test behavior when orders don't cross."""
        # Buy at low price, sell at high price (no overlap)
        buy_intent = self._create_intent("BUY", 1000000000, 3000000000, nonce=1)
        sell_intent = self._create_intent("SELL", 1000000000, 1000000000, nonce=2)
        
        self.engine.add_intent(buy_intent)
        self.engine.add_intent(sell_intent)
        
        # Force batch creation
        current_time = time.time()
        self.engine.last_batch_time = current_time - 1.0
        
        batch = self.engine.collect_intents(current_time)
        result = self.engine.compute_clearing_prices(batch)
        
        # No executions should occur
        self.assertEqual(len(result.executions), 0)
        self.assertEqual(result.total_volume, 0)


class TestSolverCompetition(unittest.TestCase):
    """Tests for SolverCompetition class."""
    
    def setUp(self):
        from solver.competition.solver_competition import SolverCompetition, SolverBid
        from core.batch.auction import Batch
        from core.intent.intent import IntentCommitment
        
        self.competition = SolverCompetition(min_solvers=2)
        self.SolverBid = SolverBid
        self.IntentCommitment = IntentCommitment
        self.Batch = Batch
    
    def test_bid_submission(self):
        """Test submitting solver bids."""
        # Create a mock batch
        batch = self.Batch(
            batch_id=0,
            intents=[],
            creation_time=time.time(),
            state_root=b'test_root'
        )
        
        # Create auction
        auction = self.competition.request_solver_bids(batch)
        
        # Submit bid
        commitment = self.IntentCommitment(
            intent_id=1,
            executed_amount=1000000000,
            execution_price=2000.0,
            route='INTERNAL'
        )
        
        bid = self.SolverBid(
            solver="0xsolver1",
            batch_id=0,
            intent_commitments=[commitment],
            clearing_prices={("ETH", "USDC"): 2000.0},
            signature="bid_sig",
            performance_bond=10000
        )
        
        result = self.competition.submit_bid(bid)
        self.assertTrue(result)
    
    def test_winner_selection(self):
        """Test deterministic winner selection."""
        # Create mock batch
        batch = self.Batch(
            batch_id=0,
            intents=[],
            creation_time=time.time(),
            state_root=b'test_root'
        )
        
        auction = self.competition.request_solver_bids(batch)
        
        # Submit multiple bids
        for i, solver in enumerate(["0xsolver1", "0xsolver2", "0xsolver3"]):
            commitment = self.IntentCommitment(
                intent_id=1,
                executed_amount=1000000000,
                execution_price=2000.0 + i * 10,  # Different prices
                route='INTERNAL'
            )
            
            bid = self.SolverBid(
                solver=solver,
                batch_id=0,
                intent_commitments=[commitment],
                clearing_prices={("ETH", "USDC"): 2000.0 + i * 10},
                signature=f"bid_sig_{i}",
                performance_bond=10000 + i * 1000
            )
            
            self.competition.submit_bid(bid)
        
        # Select winner
        winner = self.competition.select_winning_bid(0)
        
        self.assertIsNotNone(winner)
        self.assertIn(winner.solver, ["0xsolver1", "0xsolver2", "0xsolver3"])
    
    def test_anti_monopoly_rotation(self):
        """Test that winner rotation prevents monopolies."""
        winners = []
        
        for batch_id in range(10):
            batch = self.Batch(
                batch_id=batch_id,
                intents=[],
                creation_time=time.time(),
                state_root=b'test_root'
            )
            
            auction = self.competition.request_solver_bids(batch)
            
            # Submit identical bids from 3 solvers
            for solver in ["0xsolver1", "0xsolver2", "0xsolver3"]:
                commitment = self.IntentCommitment(
                    intent_id=1,
                    executed_amount=1000000000,
                    execution_price=2000.0,
                    route='INTERNAL'
                )
                
                bid = self.SolverBid(
                    solver=solver,
                    batch_id=batch_id,
                    intent_commitments=[commitment],
                    clearing_prices={("ETH", "USDC"): 2000.0},
                    signature="bid_sig",
                    performance_bond=10000
                )
                
                self.competition.submit_bid(bid)
            
            winner = self.competition.select_winning_bid(batch_id)
            winners.append(winner.solver)
        
        # Check that multiple solvers won (rotation occurred)
        unique_winners = set(winners)
        self.assertGreater(len(unique_winners), 1)


class TestStateManager(unittest.TestCase):
    """Tests for DeterministicStateManager class."""
    
    def setUp(self):
        from core.state.state_manager import DeterministicStateManager
        
        self.manager = DeterministicStateManager(snapshot_interval=100)
    
    def test_apply_batch(self):
        """Test applying a batch to state."""
        balance_changes = {
            "0x123": {"ETH": 1000000000, "USDC": -2000000000},
            "0x456": {"ETH": -1000000000, "USDC": 2000000000}
        }
        
        delta = self.manager.apply_batch(
            batch_id=0,
            balance_changes=balance_changes,
            intent_completions=[1, 2, 3],
            solver_stake_updates={"0xsolver1": 10000}
        )
        
        self.assertEqual(delta.batch_id, 0)
        self.assertIsNotNone(delta.new_state_root)
    
    def test_state_root_deterministic(self):
        """Test that state root computation is deterministic."""
        balance_changes = {
            "0x123": {"ETH": 1000000000}
        }
        
        # Apply same changes twice
        self.manager.apply_batch(0, balance_changes, [], {})
        root1 = self.manager.state_root
        
        # Reset and apply again
        self.manager = type(self.manager)(snapshot_interval=100)
        self.manager.apply_batch(0, balance_changes, [], {})
        root2 = self.manager.state_root
        
        self.assertEqual(root1, root2)
    
    def test_balance_queries(self):
        """Test balance queries after state updates."""
        balance_changes = {
            "0x123": {"ETH": 1000000000, "USDC": 5000000000}
        }
        
        self.manager.apply_batch(0, balance_changes, [], {})
        
        eth_balance = self.manager.get_balance("0x123", "ETH")
        usdc_balance = self.manager.get_balance("0x123", "USDC")
        
        self.assertEqual(eth_balance, 1000000000)
        self.assertEqual(usdc_balance, 5000000000)
    
    def test_state_reconstruction(self):
        """Test reconstructing state from event log."""
        # Apply several batches
        for i in range(5):
            balance_changes = {
                f"0x{i:03x}": {"ETH": 1000000000 * (i + 1)}
            }
            self.manager.apply_batch(i, balance_changes, [i], {})
        
        # Store original state root
        original_root = self.manager.state_root
        
        # Reconstruct state to batch 4
        success = self.manager.reconstruct_state(4)
        
        self.assertTrue(success)
        # State root should match after reconstruction
        computed_root = self.manager.compute_state_root()
        self.assertEqual(computed_root, original_root)


if __name__ == '__main__':
    unittest.main()
