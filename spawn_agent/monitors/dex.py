"""
DEX (Decentralized Exchange) monitor for tracking swap activity.

Monitors liquidity pools and DEX routers for swap events, liquidity
additions/removals, and price impact analysis.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any, Optional

from spawn_agent.monitors.base import BaseMonitor

logger = logging.getLogger(__name__)

# Common DEX event topics
SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
MINT_TOPIC = "0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f"
BURN_TOPIC = "0xdccd412f0b1252819cb1fd330b93224ca42612892bb3f4f789976e6d81936496"
SYNC_TOPIC = "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"


class DEXMonitor(BaseMonitor):
    """
    Monitors a DEX liquidity pool or router contract.

    Tracks:
        - Swap events with volume and price impact
        - Liquidity additions and removals
        - Reserve synchronization (price tracking)
        - Large swaps exceeding configurable thresholds

    Events emitted:
        - ``swap``: A swap occurred on the monitored pool
        - ``large_swap``: A swap exceeding the volume threshold
        - ``liquidity_add``: Liquidity was added to the pool
        - ``liquidity_remove``: Liquidity was removed from the pool
        - ``reserve_update``: Pool reserves were synchronized
    """

    def __init__(
        self,
        address: str,
        label: Optional[str] = None,
        provider: Any = None,
        options: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(address, label, provider, options)
        self._large_swap_threshold = Decimal(
            str(self.options.get("large_swap_threshold", "5.0"))
        )
        self._last_reserves: Optional[tuple[int, int]] = None
        self._swap_count = 0

    async def _run(self) -> None:
        """Main polling loop for DEX monitoring."""
        logger.info("DEX monitor started for pool %s (%s)", self.label, self.address)

        self._last_block = await self._get_current_block()

        while self._running:
            try:
                await self._poll_cycle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in DEX monitor for %s: %s", self.address, exc)
            await asyncio.sleep(self._poll_interval)

    async def _poll_cycle(self) -> None:
        """Fetch and process DEX events."""
        if self.provider is None:
            return

        current_block = await self._get_current_block()
        if self._last_block is None or current_block <= self._last_block:
            return

        # Fetch all relevant logs from the pool
        try:
            logs = await self.provider.get_logs(
                from_block=self._last_block + 1,
                to_block=current_block,
                contract_address=self.address,
                topics=[[SWAP_TOPIC, MINT_TOPIC, BURN_TOPIC, SYNC_TOPIC]],
            )
        except Exception:
            logs = []

        for log_entry in logs:
            topics = log_entry.get("topics", [])
            if not topics:
                continue

            event_topic = topics[0]

            if event_topic == SWAP_TOPIC:
                await self._handle_swap(log_entry)
            elif event_topic == MINT_TOPIC:
                await self._handle_mint(log_entry)
            elif event_topic == BURN_TOPIC:
                await self._handle_burn(log_entry)
            elif event_topic == SYNC_TOPIC:
                await self._handle_sync(log_entry)

        self._last_block = current_block

    async def _handle_swap(self, log_entry: dict[str, Any]) -> None:
        """Process a Swap event."""
        data = log_entry.get("data", "0x")
        topics = log_entry.get("topics", [])

        # Decode Uniswap V2 Swap event data
        try:
            sender = "0x" + topics[1][-40:] if len(topics) > 1 else None
            to = "0x" + topics[2][-40:] if len(topics) > 2 else None

            # data contains: amount0In, amount1In, amount0Out, amount1Out
            hex_data = data[2:] if data.startswith("0x") else data
            if len(hex_data) >= 256:
                amount0_in = int(hex_data[0:64], 16)
                amount1_in = int(hex_data[64:128], 16)
                amount0_out = int(hex_data[128:192], 16)
                amount1_out = int(hex_data[192:256], 16)
            else:
                amount0_in = amount1_in = amount0_out = amount1_out = 0

        except (ValueError, IndexError):
            return

        self._swap_count += 1

        event_data = {
            "sender": sender,
            "to": to,
            "amount0_in": amount0_in,
            "amount1_in": amount1_in,
            "amount0_out": amount0_out,
            "amount1_out": amount1_out,
            "block_number": log_entry.get("blockNumber"),
            "tx_hash": log_entry.get("transactionHash"),
            "swap_number": self._swap_count,
        }

        await self._emit("swap", event_data)

        # Check for large swap
        total_value = max(amount0_in + amount1_in, amount0_out + amount1_out)
        value_eth = Decimal(total_value) / Decimal(10**18)
        if value_eth >= self._large_swap_threshold:
            await self._emit("large_swap", {**event_data, "estimated_value_eth": float(value_eth)})

    async def _handle_mint(self, log_entry: dict[str, Any]) -> None:
        """Process a Mint (liquidity addition) event."""
        await self._emit(
            "liquidity_add",
            {
                "block_number": log_entry.get("blockNumber"),
                "tx_hash": log_entry.get("transactionHash"),
                "data": log_entry.get("data"),
            },
        )

    async def _handle_burn(self, log_entry: dict[str, Any]) -> None:
        """Process a Burn (liquidity removal) event."""
        await self._emit(
            "liquidity_remove",
            {
                "block_number": log_entry.get("blockNumber"),
                "tx_hash": log_entry.get("transactionHash"),
                "data": log_entry.get("data"),
            },
        )

    async def _handle_sync(self, log_entry: dict[str, Any]) -> None:
        """Process a Sync (reserve update) event."""
        data = log_entry.get("data", "0x")
        hex_data = data[2:] if data.startswith("0x") else data

        try:
            reserve0 = int(hex_data[0:64], 16)
            reserve1 = int(hex_data[64:128], 16)
        except (ValueError, IndexError):
            return

        self._last_reserves = (reserve0, reserve1)

        await self._emit(
            "reserve_update",
            {
                "reserve0": reserve0,
                "reserve1": reserve1,
                "block_number": log_entry.get("blockNumber"),
            },
        )

    @property
    def swap_count(self) -> int:
        """Total swaps observed."""
        return self._swap_count

    @property
    def last_reserves(self) -> Optional[tuple[int, int]]:
        """Last observed reserve values."""
        return self._last_reserves
