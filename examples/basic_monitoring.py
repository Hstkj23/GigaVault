#!/usr/bin/env python3
"""
Basic wallet monitoring example.

Demonstrates how to set up SpawnAgent to monitor wallet addresses
and react to on-chain events.
"""

import asyncio
import os

from spawn_agent import SpawnAgent


async def main():
    rpc_url = os.getenv("SPAWN_AGENT_RPC_URL", "https://eth.llamarpc.com")

    agent = SpawnAgent.create(
        rpc_url=rpc_url,
        chain_id=1,
        log_level="INFO",
    )

    # --- Add addresses to monitor ---

    agent.watch(
        "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68",
        label="Binance 14",
    )
    agent.watch(
        "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8",
        label="Binance 7",
    )

    # --- Register event handlers ---

    @agent.on("transfer_in")
    async def on_incoming(event):
        print(
            f"[IN]  {event.get('label', event['address'])} received "
            f"{event['value_eth']:.4f} ETH from {event['from_address']}"
        )

    @agent.on("transfer_out")
    async def on_outgoing(event):
        print(
            f"[OUT] {event.get('label', event['address'])} sent "
            f"{event['value_eth']:.4f} ETH to {event['to_address']}"
        )

    @agent.on("large_transfer")
    async def on_large(event):
        print(
            f"[!!!] LARGE TRANSFER: {event['value_eth']:.2f} ETH "
            f"({event['from_address'][:10]}... → {event['to_address'][:10]}...)"
        )

    @agent.on("balance_change")
    async def on_balance(event):
        print(
            f"[BAL] {event.get('label', event['address'])} "
            f"balance: {event['new_balance_eth']:.4f} ETH "
            f"(Δ {event['delta_eth']:+.4f})"
        )

    # --- Start monitoring ---

    print(f"SpawnAgent starting — monitoring {agent.monitor_count} addresses...")
    print("Press Ctrl+C to stop.\n")

    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
