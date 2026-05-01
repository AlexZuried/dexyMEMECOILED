# APEX Protocol Architecture

## Overview

APEX (Adversarial-Proof Exchange) is a production-grade decentralized exchange achieving ~zero protocol cost through radical externalization of all operational responsibilities to profit-seeking actors.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    APEX PROTOCOL LAYERS                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────┐    ┌───────────┐    ┌───────────┐          │
│  │ TRADERS   │    │ SOLVERS   │    │ RELAYERS  │          │
│  │ (Intent)  │    │ (Execute) │    │ (Propagate)│         │
│  └─────┬─────┘    └─────┬─────┘    └─────┬─────┘          │
│        │                │                │                 │
│        ▼                ▼                ▼                 │
│  ┌─────────────────────────────────────────────────┐       │
│  │           INTENT GOSSIP LAYER (P2P)             │       │
│  │  • libp2p-based propagation                     │       │
│  │  • Stake-based rate limiting                    │       │
│  │  • Deterministic batching (200ms windows)       │       │
│  └─────────────────────────────────────────────────┘       │
│                          │                                  │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────┐       │
│  │           BATCH AUCTION ENGINE                  │       │
│  │  • Uniform price clearing                       │       │
│  │  • Solver competition                           │       │
│  │  • Anti-cartel mechanisms                       │       │
│  └─────────────────────────────────────────────────┘       │
│                          │                                  │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────┐       │
│  │        SETTLEMENT & CHALLENGE LAYER             │       │
│  │  • On-chain settlement (minimal)                │       │
│  │  • 5-minute challenge window                    │       │
│  │  • Watcher incentives                           │       │
│  └─────────────────────────────────────────────────┘       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Intent Layer (`core/intent/`)

- **TradingIntent**: Signed expression of trading desire
- **IntentValidator**: Stake-based spam prevention
- **Reputation System**: Dynamic stake requirements based on history

### 2. Batch Auction (`core/batch/`)

- **BatchAuctionEngine**: Deterministic batch creation and clearing
- **Uniform Price Clearing**: All matched orders execute at same price
- **Price Discovery**: Supply/demand intersection algorithm

### 3. State Management (`core/state/`)

- **DeterministicStateManager**: No database, state from events
- **Compressed Snapshots**: Fast sync for new nodes
- **Merkle Proofs**: Cryptographic state verification

### 4. Solver Competition (`solver/competition/`)

- **SolverCompetition**: Fair selection mechanism
- **Anti-Monopoly Rotation**: Prevents solver cartels
- **Performance Tracking**: Historical metrics for selection

## Data Flow

1. **Intent Creation**: Trader signs intent with stake deposit
2. **Gossip Propagation**: Relayers propagate to network
3. **Batch Collection**: Solvers collect intents into batches
4. **Solver Bidding**: Solvers submit price improvement bids
5. **Winner Selection**: Deterministic selection based on score
6. **Execution**: Winner executes via internal/external routes
7. **Settlement**: On-chain settlement with proofs
8. **Challenge Window**: Watchers can challenge fraudulent executions
9. **Finalization**: State update after challenge period

## Security Model

### Economic Security
- Stake-based spam prevention
- Slashing for misbehavior
- Challenge rewards (50% of slash)

### Technical Security
- Deterministic execution
- Replay attack prevention
- Merkle state proofs

### Adversarial Resistance
- Cartel detection algorithms
- Geographic latency fairness
- Partition tolerance

## Incentive Design

### Solvers Earn:
- 70% of trading fees (from 0.04% protocol fee)
- Price improvement capture
- Liquidation fees (5%)
- Cross-chain arbitrage profits

### Relayers Earn:
- Per-message delivery fees
- Diversity bonuses
- Snapshot serving fees

### Watchers Earn:
- 50% of slashed amounts
- Monitoring subscriptions (optional)

## Trade-offs

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Latency | 200ms batches | Fairness over speed |
| Finality | 5-min challenge | Security over instant finality |
| State | Event-sourced | Resilience over query speed |
| Matching | Uniform price | Simplicity and fairness |

## Getting Started

See [README.md](../README.md) for installation and usage instructions.
