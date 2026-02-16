#!/usr/bin/env python3
"""
Custom alert handler example.

Demonstrates how to implement a custom alert handler and integrate
it with SpawnAgent's alert dispatcher.
"""

import asyncio
import json
import os
from datetime import datetime, timezone

from spawn_agent import SpawnAgent
from spawn_agent.alerts.base import Alert, AlertHandler
from spawn_agent.alerts.dispatcher import AlertDispatcher


class FileAlertHandler(AlertHandler):
    """Write alerts to a JSON Lines file for audit logging.

    Each alert is appended as a single JSON line, making it easy to
    process with standard Unix tools (grep, jq, etc.).
    """

    def __init__(self, filepath: str = "alerts.jsonl"):
        super().__init__(name="file")
        self.filepath = filepath

    async def send(self, alert: Alert) -> bool:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **alert.to_dict(),
        }
        line = json.dumps(record, default=str) + "\n"

        # In production, consider using aiofiles for non-blocking I/O.
        # For simplicity, this example uses synchronous writes.
        with open(self.filepath, "a") as f:
            f.write(line)

        return True


class ConsoleAlertHandler(AlertHandler):
    """Pretty-print alerts to the console with color coding."""

    COLORS = {
        "info": "\033[36m",      # Cyan
        "warning": "\033[33m",   # Yellow
        "critical": "\033[31m",  # Red
    }
    RESET = "\033[0m"

    def __init__(self):
        super().__init__(name="console")

    async def send(self, alert: Alert) -> bool:
        color = self.COLORS.get(alert.severity, "")
        prefix = f"{color}[{alert.severity.upper()}]{self.RESET}"
        print(f"{prefix} {alert.title}: {alert.message}")
        if alert.address:
            print(f"  Address: {alert.address}")
        if alert.tx_hash:
            print(f"  Tx:      {alert.tx_hash}")
        return True


async def main():
    rpc_url = os.getenv("SPAWN_AGENT_RPC_URL", "https://eth.llamarpc.com")

    agent = SpawnAgent.create(rpc_url=rpc_url, chain_id=1)

    # --- Set up custom alert pipeline ---

    dispatcher = AlertDispatcher(dedup_window=120.0)
    dispatcher.register(ConsoleAlertHandler())
    dispatcher.register(FileAlertHandler("spawn_alerts.jsonl"))

    # --- Wire events to alerts ---

    @agent.on("large_transfer")
    async def alert_large_transfer(event):
        await dispatcher.dispatch(
            Alert(
                title="Large Transfer Detected",
                message=(
                    f"{event.get('value_eth', 0):.2f} ETH moved "
                    f"from {event['from_address'][:10]}... "
                    f"to {event['to_address'][:10]}..."
                ),
                severity="warning",
                address=event["address"],
                tx_hash=event.get("tx_hash"),
                metadata={"value_wei": event.get("value_wei")},
            )
        )

    @agent.on("new_interaction")
    async def alert_new_interaction(event):
        await dispatcher.dispatch(
            Alert(
                title="New Wallet Interaction",
                message=f"First interaction with {event.get('counterparty', 'unknown')}",
                severity="info",
                address=event["address"],
            )
        )

    # --- Monitor some addresses ---

    agent.watch(
        "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68",
        label="Exchange Hot Wallet",
    )

    print("Starting SpawnAgent with custom alert handlers...")
    print("Alerts will be printed to console and logged to spawn_alerts.jsonl")
    print("Press Ctrl+C to stop.\n")

    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
