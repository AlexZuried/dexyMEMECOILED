# APEX Protocol - Adversarial-Proof Exchange

## Overview

APEX is a production-grade decentralized exchange (DEX) architecture achieving ~zero protocol cost through radical externalization of all operational responsibilities to profit-seeking actors.

## Core Principles

1. **Self-Sustaining Economics**: No token inflation, no subsidies, all actors profit-driven
2. **Permissionless Infrastructure**: Anyone can become solver, relayer, or watcher
3. **Zero-Cost Infra Model**: No centralized servers, state is reconstructible
4. **Deterministic Execution**: All matching logic is deterministic and replayable
5. **Minimal On-Chain Footprint**: Chain used only for settlement and disputes

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    APEX PROTOCOL LAYERS                     │
├─────────────────────────────────────────────────────────────┤
│  TRADERS → INTENT GOSSIP → BATCH AUCTION → SETTLEMENT      │
│     ↓          ↓              ↓              ↓              │
│  Stake    P2P Prop      Solver Comp    On-Chain + Challenge│
└─────────────────────────────────────────────────────────────┘
```

## Directory Structure

- `contracts/` - Smart contracts for settlement and disputes
- `core/` - Core protocol logic
  - `batch/` - Batch auction engine
  - `matching/` - Order matching algorithms
  - `state/` - Deterministic state management
  - `intent/` - Intent structures and validation
- `network/` - P2P networking layer
  - `gossip/` - Intent gossip protocol
  - `relayer/` - Relay network implementation
- `solver/` - Solver implementations
  - `engine/` - Execution engine
  - `competition/` - Solver competition logic
  - `liquidation/` - Liquidation engine
- `watcher/` - Fraud detection and monitoring
  - `challenge/` - Challenge system
  - `monitoring/` - System monitoring
- `utils/` - Utility functions
- `tests/` - Test suite
- `docs/` - Documentation
- `scripts/` - Deployment and utility scripts

## Key Features

### Intent-Based Trading
Traders express *what* they want, not *how* to execute. Solvers compete to provide best execution.

### Batch Auctions
Deterministic batching (100-500ms windows) with uniform price clearing for fairness and MEV resistance.

### Solver Competition
Multiple solvers compete on price improvement, stake, and historical performance.

### Challenge-Based Security
Watchers monitor settlements and can challenge fraudulent executions with economic incentives.

### Zero Database State
State = snapshot + deterministic deltas. Fully reconstructible from event logs.

## Getting Started

### Prerequisites
- Python 3.9+
- Node.js 18+ (for frontend)
- Rust (optional, for performance-critical components)

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/

# Start a solver node
python scripts/run_solver.py

# Start a relayer node
python scripts/run_relayer.py
```

## Incentive Model

### Solvers Earn Through:
- Trading fee share (70% of 0.04% protocol fee)
- Price improvement capture (spread between committed and executed price)
- Liquidation fees (5% of liquidated position value)
- Cross-chain arbitrage profits

### Relayers Earn Through:
- Per-message delivery fees
- Network health bonuses (diversity incentives)
- Snapshot serving fees
- Propagation bonuses

### Watchers Earn Through:
- Successful challenge rewards (50% of slashed amount)
- Monitoring subscription fees (optional)
- Governance participation rewards

## Anti-Abuse Mechanisms

- **Stake-based spam prevention**: Dynamic stake requirements based on reputation
- **Slashing conditions**: Explicit penalties for misbehavior
- **Replay attack prevention**: Nonce tracking and message deduplication
- **Griefing resistance**: High bonds for challenges, automatic compensation

## Trade-offs

| Trade-off | Decision | Justification |
|-----------|----------|---------------|
| Latency vs Fairness | 200ms batch windows | Prevents latency arbitrage, ensures geographic fairness |
| Complexity vs Decentralization | Complex solver requirements | Necessary for professional execution, still permissionless |
| Challenge Window vs Finality | 5-minute window | Critical for security, most trades don't need instant finality |
| State Reconstruction vs Query Speed | No database | Eliminates single point of failure, snapshots provide fast access |

## License

MIT

## Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for contribution guidelines.
