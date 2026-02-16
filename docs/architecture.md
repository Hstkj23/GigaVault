# Architecture

SpawnAgent is built around an **OTP-inspired supervision model** adapted for
Python's asyncio runtime. This document describes the key architectural decisions
and how the components fit together.

## Overview

```
┌────────────────────────────────────────────────┐
│                  SpawnAgent                     │
│                                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ Monitors │──│ Pipeline │──│ Alert Engine │ │
│  └────┬─────┘  └──────────┘  └──────────────┘ │
│       │                                        │
│  ┌────┴──────────────────────────────┐         │
│  │         Supervisor Tree           │         │
│  │  ┌────────┐ ┌────────┐ ┌───────┐ │         │
│  │  │Worker 1│ │Worker 2│ │Worker…│ │         │
│  │  └────────┘ └────────┘ └───────┘ │         │
│  └───────────────────────────────────┘         │
│                                                │
│  ┌────────────┐  ┌────────────────────┐        │
│  │  Providers │  │ Analysis Engine    │        │
│  │  (RPC/WS)  │  │ (Graph, Anomaly,  │        │
│  │            │  │  Patterns, Cluster)│        │
│  └────────────┘  └────────────────────┘        │
└────────────────────────────────────────────────┘
```

## Core Concepts

### Supervisor Tree

Inspired by Erlang/OTP supervisors, the supervision tree manages worker process
lifecycles with automatic fault recovery.

**Restart Strategies:**

| Strategy      | Behavior                                         |
|---------------|--------------------------------------------------|
| ONE_FOR_ONE   | Only the failed worker is restarted              |
| ONE_FOR_ALL   | All workers are restarted when one fails         |
| REST_FOR_ONE  | The failed worker and all workers started after it are restarted |

The supervisor implements a **circuit breaker**: if a worker restarts more than
`max_restarts` times within `restart_window` seconds, it is permanently terminated
to prevent restart storms.

### Worker Processes

Each monitored address runs as an isolated `WorkerProcess`. Workers:
- Have independent lifecycles (start, stop, restart)
- Maintain their own state (last seen block, event count)
- Emit events through a callback function
- Report health status to their supervisor

### Pipeline

Events flow through a multi-stage `Pipeline` with bounded queues between stages.
Each stage can:
- Transform events (modify and forward)
- Filter events (return `None` to drop)
- Fan out (return multiple events)

Backpressure is applied automatically when downstream stages can't keep up.

### Providers

Providers abstract the blockchain data source:

- **RPCProvider**: JSON-RPC over HTTP with connection pooling, retry logic,
  request batching, and rate limiting
- **WebSocketProvider**: Persistent WebSocket connection for `newHeads`,
  `pendingTransactions`, and `logs` subscriptions with auto-reconnect

### Monitors

Monitors implement the actual on-chain observation logic:

| Monitor   | Tracks                                    |
|-----------|-------------------------------------------|
| Wallet    | ETH transfers, ERC-20 transfers, balance  |
| Contract  | Function calls, events, new callers       |
| Mempool   | Pending transactions, large transfers     |
| DEX       | Swap, Mint, Burn, Sync events             |

### Analysis Engine

Four analysis modules process event streams:

- **Graph**: Builds a directed transaction graph for tracing fund flows
- **Anomaly**: Detects volume spikes, rapid transactions, circular flows
- **Patterns**: Identifies known on-chain patterns (sandwich attacks, rug pulls)
- **Cluster**: Groups related wallets by funding source and behavior

### Alert System

Alerts are dispatched through a fan-out dispatcher with:
- SHA-256 deduplication (suppresses identical alerts within a window)
- Per-severity rate limiting
- Multiple output channels (Telegram, Discord, Webhook)
- Bounded queue to prevent memory growth

## Data Flow

```
Block/Mempool → Monitor → Event → Pipeline → Analysis → Alert
                  ↑                              ↓
              Supervisor                    Dispatcher
              (lifecycle)                  (fan-out)
```

1. **Ingestion**: Monitors poll or subscribe to new blocks/transactions
2. **Detection**: Raw chain data is processed into typed events
3. **Analysis**: Events pass through the analysis pipeline
4. **Alerting**: Significant findings are dispatched to configured channels

## Configuration

All components are configurable via YAML with environment variable overrides.
See `config/spawn_agent.example.yml` for the full schema.

## Threading Model

SpawnAgent is **single-threaded, async** — all concurrency is cooperative via
`asyncio`. This avoids lock contention and matches the I/O-bound nature of
blockchain monitoring. CPU-bound analysis (graph algorithms, clustering) runs
in `asyncio.to_thread()` when processing large datasets.
