#!/usr/bin/env python3
"""
APEX Protocol - Relayer Node Runner

Starts a relayer node that propagates intents and batches.
"""

import sys
import time
import signal
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('apex.relayer')


class RelayerNode:
    """Relayer node that propagates messages in the P2P network."""
    
    def __init__(self, relayer_id: str, port: int = 9000):
        self.relayer_id = relayer_id
        self.port = port
        self.running = False
        self.messages_relayed = 0
        
        logger.info(f"Relayer node initialized: {relayer_id}")
        logger.info(f"Listening on port: {port}")
    
    def start(self):
        """Start the relayer node."""
        self.running = True
        logger.info("Relayer node started")
        
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        try:
            while self.running:
                self._run_cycle()
                time.sleep(0.05)  # 50ms cycle for low latency
        except Exception as e:
            logger.error(f"Relayer error: {e}")
            raise
        finally:
            self.stop()
    
    def _run_cycle(self):
        """Single relayer cycle."""
        # In production:
        # 1. Listen for new intents/messages from peers
        # 2. Validate message signatures and stakes
        # 3. Propagate to connected peers (flooding algorithm)
        # 4. Track relay metrics for rewards
        pass
    
    def stop(self):
        """Stop the relayer node."""
        self.running = False
        logger.info(f"Relayer node stopped. Total messages relayed: {self.messages_relayed}")
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='APEX Relayer Node')
    parser.add_argument('--id', type=str, required=True,
                       help='Unique relayer identifier')
    parser.add_argument('--port', type=int, default=9000,
                       help='Port to listen on')
    parser.add_argument('--peers', type=str, nargs='*',
                       help='Initial peer addresses to connect to')
    
    args = parser.parse_args()
    
    relayer = RelayerNode(args.id, args.port)
    
    try:
        relayer.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
