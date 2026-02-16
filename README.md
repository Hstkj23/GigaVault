<div align="center">

<img src="docs/assets/spawn_logo.png" alt="SpawnAgent" width="120"/>

# SpawnAgent

**Real-time on-chain intelligence and wallet monitoring platform.**

[![CI](https://github.com/Hstkj23/GigaVault/actions/workflows/ci.yml/badge.svg)](https://github.com/Hstkj23/GigaVault/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Hstkj23/GigaVault/branch/main/graph/badge.svg)](https://codecov.io/gh/Hstkj23/GigaVault)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[Quickstart](#quickstart) · [Documentation](docs/) · [Examples](examples/) · [Contributing](CONTRIBUTING.md)

</div>

---

## Overview

SpawnAgent is an open-source, self-hosted platform for monitoring blockchain wallets, tracing fund flows, and detecting anomalous on-chain activity in real-time. It is designed around a concurrent process-per-wallet architecture — each monitored address runs as an independent, supervised async worker that streams events, analyzes patterns, and dispatches alerts with sub-second latency.

SpawnAgent was built for researchers, analysts, and developers who need reliable, programmatic access to on-chain intelligence without depending on centralized third-party dashboards.

### Why SpawnAgent?

- **Process-per-wallet concurrency** — monitor tens of thousands of addresses simultaneously using Python's `asyncio` with structured supervision trees
- **Real-time streaming** — WebSocket-first architecture pushes events the moment they land on-chain
- **Wallet graph analysis** — trace fund flows across hops, cluster related wallets, and visualize transaction graphs
- **Anomaly detection** — built-in heuristic + ML-based detectors for unusual volume spikes, wash trading patterns, and coordinated wallet activity
- **Pluggable alert system** — route alerts to Telegram, Discord, webhooks, or custom handlers
- **Self-hosted & private** — your data stays on your infrastructure, no external API keys required beyond an RPC endpoint
- **Extensible** — write custom monitors, detectors, and alert handlers as simple Python classes

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   SpawnAgent Core                    │
├──────────┬──────────┬──────────┬────────────────────┤
│ Monitors │ Analysis │ Providers│     Alerts          │
│          │          │          │                     │
│ Wallet   │ Graph    │ RPC      │ Telegram            │
│ Contract │ Anomaly  │ WebSocket│ Discord             │
│ Mempool  │ Patterns │ REST API │ Webhook             │
│ DEX      │ Cluster  │ Archive  │ Custom handlers     │
└────┬─────┴────┬─────┴────┬─────┴──────────┬─────────┘
     │          │          │                │
     ▼          ▼          ▼                ▼
┌─────────┐┌────────┐┌──────────┐   ┌────────────┐
│Supervisor││Pipeline││ Provider │   │ Dispatcher │
│  Tree    ││ Engine ││  Pool    │   │            │
└─────────┘└────────┘└──────────┘   └────────────┘
```

## Quickstart

### Installation

```bash
# Clone the repository
git clone https://github.com/Hstkj23/GigaVault.git spawn_agent
cd spawn_agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -e ".[dev]"
```

### Configuration

Copy the example configuration and set your RPC endpoint:

```bash
cp config/spawn_agent.example.yml config/spawn_agent.yml
```

```yaml
# config/spawn_agent.yml
provider:
  rpc_url: "https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"
  chain_id: 1
  max_connections: 50

monitoring:
  poll_interval: 2.0
  max_workers: 1000
  supervisor_restart_limit: 5

alerts:
  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id: "${TELEGRAM_CHAT_ID}"
```

### Basic Usage

```python
import asyncio
from spawn_agent import SpawnAgent

async def main():
    agent = SpawnAgent.from_config("config/spawn_agent.yml")

    # Monitor a wallet
    agent.watch("0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68")

    # Add a custom callback
    @agent.on("large_transfer")
    async def handle_large_transfer(event):
        print(f"Large transfer detected: {event.value_eth} ETH")
        print(f"From: {event.from_address} -> To: {event.to_address}")

    await agent.start()

asyncio.run(main())
```

### CLI

```bash
# Watch a single wallet
spawn-agent watch 0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68

# Trace fund flow from an address (3 hops deep)
spawn-agent trace 0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68 --depth 3

# Monitor all wallets from a file
spawn-agent watch --file wallets.txt --alert telegram

# Start the full monitoring dashboard
spawn-agent serve --port 8420
```

## Features

### Wallet Monitoring
Each watched address is assigned a dedicated async worker that subscribes to on-chain events via WebSocket. Workers are managed by a supervision tree that automatically restarts failed monitors with exponential backoff and circuit-breaking.

### Fund Flow Tracing
Recursively trace the origin or destination of funds across multiple hops. The tracer builds a directed graph of transactions and identifies clusters of related wallets using address co-spending analysis and temporal correlation.

### Anomaly Detection
Built-in detectors analyze transaction streams for:
- **Volume anomalies** — sudden spikes relative to historical baseline
- **Wash trading patterns** — circular fund flows within a short time window
- **Coordinated activity** — multiple wallets acting in sync (similar timing, amounts, or targets)
- **New wallet behavior** — freshly funded wallets executing unusual patterns

### Alert System
Alerts are dispatched through a pluggable handler system. Built-in handlers include Telegram, Discord, and generic webhooks. Custom handlers can be registered:

```python
from spawn_agent.alerts import AlertHandler

class SlackAlertHandler(AlertHandler):
    async def send(self, alert):
        await self.http.post(self.webhook_url, json=alert.to_dict())

agent.alerts.register(SlackAlertHandler(webhook_url="https://hooks.slack.com/..."))
```

## Project Structure

```
spawn_agent/
├── spawn_agent/           # Core Python package
│   ├── core/              # Agent orchestration, process management, supervision
│   ├── monitors/          # Wallet, contract, mempool, and DEX monitors
│   ├── analysis/          # Graph analysis, anomaly detection, pattern matching
│   ├── providers/         # RPC, WebSocket, and REST API providers
│   ├── alerts/            # Alert dispatching and notification handlers
│   ├── cli/               # Command-line interface
│   └── utils/             # Configuration, logging, type definitions
├── tests/                 # Test suite
├── docs/                  # Documentation
├── examples/              # Usage examples
├── config/                # Configuration templates
└── scripts/               # Utility scripts
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v --cov=spawn_agent

# Lint
ruff check spawn_agent/ tests/
black --check spawn_agent/ tests/

# Type checking
mypy spawn_agent/
```

## Roadmap

- [x] Core agent architecture with supervision trees
- [x] Wallet and contract monitoring
- [x] Fund flow tracing and graph analysis
- [x] Anomaly detection engine
- [x] Telegram and Discord alert handlers
- [ ] Web dashboard with real-time visualization
- [ ] Multi-chain support (Arbitrum, Base, Solana)
- [ ] Plugin system for community-contributed detectors
- [ ] Historical data backfill and replay
- [ ] REST API for integration with external tools

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to get started, coding standards, and the pull request process.

## Security

If you discover a security vulnerability, please report it responsibly. See [SECURITY.md](SECURITY.md) for details.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
