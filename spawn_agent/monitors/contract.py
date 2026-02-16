"""
Contract monitor for tracking smart contract interactions.

Monitors function calls, event emissions, and state changes
for a specific smart contract address.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from spawn_agent.monitors.base import BaseMonitor

logger = logging.getLogger(__name__)

# Common method selectors for known contract interactions
KNOWN_SELECTORS: dict[str, str] = {
    "0xa9059cbb": "transfer(address,uint256)",
    "0x23b872dd": "transferFrom(address,address,uint256)",
    "0x095ea7b3": "approve(address,uint256)",
    "0x70a08231": "balanceOf(address)",
    "0x18160ddd": "totalSupply()",
    "0x3593564c": "execute(bytes,bytes[],uint256)",  # Uniswap Universal Router
    "0x7ff36ab5": "swapExactETHForTokens(uint256,address[],address,uint256)",
    "0x38ed1739": "swapExactTokensForTokens(uint256,uint256,address[],address,uint256)",
    "0xe8e33700": "addLiquidity(address,address,uint256,uint256,uint256,uint256,address,uint256)",
    "0xf305d719": "addLiquidityETH(address,uint256,uint256,uint256,address,uint256)",
    "0xbaa2abde": "removeLiquidity(address,address,uint256,uint256,uint256,address,uint256)",
}


class ContractMonitor(BaseMonitor):
    """
    Monitors a smart contract for interactions and events.

    Tracks:
        - Function calls to the contract
        - Event log emissions
        - Contract creation and self-destruct
        - Unusual interaction patterns

    Events emitted:
        - ``contract_call``: A transaction called the contract
        - ``contract_event``: A log was emitted by the contract
        - ``high_frequency``: Interaction rate exceeds threshold
        - ``new_caller``: A new address interacted with the contract

    Args:
        address: Contract address to monitor.
        label: Human-readable label.
        provider: RPC provider instance.
        options: Configuration overrides including ABI, tracked events, etc.
    """

    def __init__(
        self,
        address: str,
        label: Optional[str] = None,
        provider: Any = None,
        options: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(address, label, provider, options)
        self._abi = self.options.get("abi")
        self._tracked_events = set(self.options.get("tracked_events", []))
        self._known_callers: set[str] = set()
        self._call_count_window: list[float] = []
        self._high_freq_threshold = self.options.get("high_freq_threshold", 50)
        self._window_seconds = self.options.get("window_seconds", 300)

    async def _run(self) -> None:
        """Main polling loop for contract monitoring."""
        logger.info("Contract monitor started for %s (%s)", self.label, self.address)

        self._last_block = await self._get_current_block()

        while self._running:
            try:
                await self._poll_cycle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "Error in contract monitor for %s: %s", self.address, exc
                )
            await asyncio.sleep(self._poll_interval)

    async def _poll_cycle(self) -> None:
        """Execute one polling cycle."""
        if self.provider is None:
            return

        current_block = await self._get_current_block()
        if self._last_block is None or current_block <= self._last_block:
            return

        # Fetch transactions to this contract
        transactions = await self._fetch_contract_calls(
            self._last_block + 1, current_block
        )

        for tx in transactions:
            await self._process_contract_call(tx)

        # Fetch logs emitted by this contract
        logs = await self._fetch_contract_logs(
            self._last_block + 1, current_block
        )

        for log_entry in logs:
            await self._process_contract_event(log_entry)

        # Check for high-frequency interaction
        await self._check_frequency()

        self._last_block = current_block

    async def _fetch_contract_calls(
        self, from_block: int, to_block: int
    ) -> list[dict[str, Any]]:
        """Fetch transactions sent to this contract."""
        try:
            return await self.provider.get_transactions(
                address=self.address,
                from_block=from_block,
                to_block=to_block,
                direction="incoming",
            )
        except Exception:
            return []

    async def _fetch_contract_logs(
        self, from_block: int, to_block: int
    ) -> list[dict[str, Any]]:
        """Fetch all logs emitted by this contract."""
        try:
            return await self.provider.get_logs(
                from_block=from_block,
                to_block=to_block,
                contract_address=self.address,
            )
        except Exception:
            return []

    async def _process_contract_call(self, tx: dict[str, Any]) -> None:
        """Process a transaction calling this contract."""
        import time

        caller = tx.get("from", "").lower()
        input_data = tx.get("input", "0x")
        method_selector = input_data[:10] if len(input_data) >= 10 else input_data

        method_name = KNOWN_SELECTORS.get(method_selector, method_selector)

        event_data = {
            "tx_hash": tx.get("hash"),
            "caller": caller,
            "method": method_name,
            "method_selector": method_selector,
            "value_wei": int(tx.get("value", 0)),
            "block_number": tx.get("blockNumber"),
            "gas_used": tx.get("gasUsed"),
        }

        await self._emit("contract_call", event_data)

        # Track new callers
        if caller not in self._known_callers:
            self._known_callers.add(caller)
            await self._emit("new_caller", {
                **event_data,
                "total_unique_callers": len(self._known_callers),
            })

        self._call_count_window.append(time.time())

    async def _process_contract_event(self, log_entry: dict[str, Any]) -> None:
        """Process a log event emitted by the contract."""
        topics = log_entry.get("topics", [])
        event_topic = topics[0] if topics else None

        # If we're tracking specific events, filter
        if self._tracked_events and event_topic not in self._tracked_events:
            return

        await self._emit(
            "contract_event",
            {
                "event_topic": event_topic,
                "topics": topics,
                "data": log_entry.get("data"),
                "block_number": log_entry.get("blockNumber"),
                "tx_hash": log_entry.get("transactionHash"),
                "log_index": log_entry.get("logIndex"),
            },
        )

    async def _check_frequency(self) -> None:
        """Check if interaction frequency exceeds threshold."""
        import time

        cutoff = time.time() - self._window_seconds
        self._call_count_window = [
            t for t in self._call_count_window if t > cutoff
        ]

        if len(self._call_count_window) >= self._high_freq_threshold:
            await self._emit(
                "high_frequency",
                {
                    "calls_in_window": len(self._call_count_window),
                    "window_seconds": self._window_seconds,
                    "unique_callers": len(self._known_callers),
                },
            )

    @property
    def unique_callers(self) -> int:
        """Number of unique addresses that have called this contract."""
        return len(self._known_callers)
