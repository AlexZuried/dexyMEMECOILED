#!/usr/bin/env python3
"""
APEX Protocol - Solver Node Runner

Starts a solver node that participates in batch auctions.
"""

import sys
import time
import signal
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('apex.solver')


class SolverNode:
    """Solver node that competes for batch execution."""
    
    def __init__(self, solver_address: str, stake: int):
        self.solver_address = solver_address
        self.stake = stake
        self.running = False
        
        logger.info(f"Solver node initialized: {solver_address}")
        logger.info(f"Initial stake: {stake}")
    
    def start(self):
        """Start the solver node."""
        self.running = True
        logger.info("Solver node started")
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        try:
            while self.running:
                # Main solver loop
                self._run_cycle()
                time.sleep(0.1)  # 100ms cycle
        except Exception as e:
            logger.error(f"Solver error: {e}")
            raise
        finally:
            self.stop()
    
    def _run_cycle(self):
        """Single solver cycle."""
        # In production, this would:
        # 1. Listen for new batches from P2P network
        # 2. Compute optimal execution strategy
        # 3. Submit bid with price improvements
        # 4. If selected, execute batch and settle
        pass
    
    def stop(self):
        """Stop the solver node."""
        self.running = False
        logger.info("Solver node stopped")
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='APEX Solver Node')
    parser.add_argument('--address', type=str, required=True,
                       help='Solver address (public key)')
    parser.add_argument('--stake', type=int, default=10000,
                       help='Initial stake amount')
    parser.add_argument('--network', type=str, default='mainnet',
                       choices=['mainnet', 'testnet', 'local'],
                       help='Network to connect to')
    
    args = parser.parse_args()
    
    solver = SolverNode(args.address, args.stake)
    
    try:
        solver.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
