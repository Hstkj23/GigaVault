# Quickstart Guide

Get SpawnAgent running in under 5 minutes.

## Prerequisites

- Python 3.10 or later
- An Ethereum RPC endpoint (Alchemy, Infura, or self-hosted node)

## Installation

### From source

```bash
git clone https://github.com/Hstkj23/GigaVault.git
cd GigaVault
pip install -e ".[dev]"
```

### From PyPI (when published)

```bash
pip install spawn-agent
```

## Configuration

Copy the example config:

```bash
cp config/spawn_agent.example.yml config/spawn_agent.yml
```

Set your RPC URL:

```bash
export SPAWN_AGENT_RPC_URL="https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"
```

Or edit `config/spawn_agent.yml` directly.

## Basic Usage

### Python API

```python
import asyncio
from spawn_agent import SpawnAgent

async def main():
    agent = SpawnAgent.create(
        rpc_url="https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY",
        chain_id=1,
    )

    # Watch a wallet
    agent.watch("0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68", label="Binance 14")

    # Register event handler
    @agent.on("large_transfer")
    async def on_large_transfer(event):
        print(f"Large transfer detected: {event}")

    await agent.start()

asyncio.run(main())
```

### CLI

```bash
# Watch an address
spawn-agent watch 0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68

# Trace fund flows
spawn-agent trace 0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68 --depth 3

# Start the monitoring service
spawn-agent serve --config config/spawn_agent.yml
```

### Docker

```bash
# Set your RPC URL in .env
echo "SPAWN_AGENT_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY" > .env

# Start
docker compose up -d
```

## Setting Up Alerts

### Telegram

1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Get your chat ID from [@userinfobot](https://t.me/userinfobot)
3. Set environment variables:
   ```bash
   export SPAWN_AGENT_TELEGRAM_BOT_TOKEN="your-bot-token"
   export SPAWN_AGENT_TELEGRAM_CHAT_ID="your-chat-id"
   ```

### Discord

1. Create a webhook in your Discord channel settings
2. Set the webhook URL:
   ```bash
   export SPAWN_AGENT_DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
   ```

## Next Steps

- Read the [Architecture](architecture.md) docs to understand the internals
- Browse the [API Reference](api.md) for detailed class documentation
- Check the `examples/` directory for more usage patterns
