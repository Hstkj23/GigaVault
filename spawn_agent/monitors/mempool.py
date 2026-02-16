"""
Mempool monitor for tracking pending transactions.

Subscribes to the pending transaction pool (txpool) to detect
transactions before they are confirmed on-chain.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any, Optional

from spawn_agent.monitors.base import BaseMonitor

logger = logging.getLogger(__name__)


class MempoolMonitor(BaseMonitor):
    """
    Monitors the mempool for pending transactions involving watched addresses.

    This monitor connects to a node's pending transaction stream and
    filters for transactions relevant to the configured address. It
    enables pre-confirmation alerting for large transfers, contract
    interactions, and MEV-related activity.

    Events emitted:
        - ``pending_tx``: A pending transaction was detected
        - ``pending_large_transfer``: A large pending transfer
        - ``pending_contract_interaction``: Pending call to a contract

    Note:
        Requires a WebSocket connection to a full node with ``newPendingTransactions``
        subscription support. Not all RPC providers support this.
    """

    def __init__(
        self,
        address: str,
        label: Optional[str] = None,
        provider: Any = None,
        options: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(address, label, provider, options)
        self._watched_addresses: set[str] = {self.address}
        self._large_threshold = Decimal(
            str(self.options.get("large_transfer_threshold", "10.0"))
        )
        self._seen_hashes: set[str] = set()
        self._max_seen_cache = self.options.get("max_seen_cache", 100_000)

    def add_watched_address(self, address: str) -> None:
        """Add an address to the mempool watch list."""
        self._watched_addresses.add(address.lower())

    def remove_watched_address(self, address: str) -> None:
        """Remove an address from the mempool watch list."""
        self._watched_addresses.discard(address.lower())

    async def _run(self) -> None:
        """Main loop: subscribe to pending transactions."""
        logger.info(
            "Mempool monitor started, watching %d addresses",
            len(self._watched_addresses),
        )

        while self._running:
            try:
                await self._subscribe_pending()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Mempool subscription error: %s", exc)
                await asyncio.sleep(5.0)  # Reconnect delay

    async def _subscribe_pending(self) -> None:
        """Subscribe to pending transactions via WebSocket."""
        if self.provider is None:
            raise RuntimeError("No provider configured for mempool monitoring")

        async for tx_hash in self.provider.subscribe_pending_transactions():
            if not self._running:
                break

            if tx_hash in self._seen_hashes:
                continue

            self._seen_hashes.add(tx_hash)

            # Prune seen cache
            if len(self._seen_hashes) > self._max_seen_cache:
                # Remove oldest ~20% of entries
                to_remove = len(self._seen_hashes) - int(self._max_seen_cache * 0.8)
                for _ in range(to_remove):
                    self._seen_hashes.pop()

            # Fetch full transaction details
            try:
                tx = await self.provider.get_transaction(tx_hash)
                if tx is None:
                    continue
            except Exception:
                continue

            await self._process_pending_tx(tx)

    async def _process_pending_tx(self, tx: dict[str, Any]) -> None:
        """Process a pending transaction and filter for relevance."""
        from_addr = tx.get("from", "").lower()
        to_addr = tx.get("to", "").lower()

        # Check if this transaction involves any watched address
        if from_addr not in self._watched_addresses and to_addr not in self._watched_addresses:
            return

        value_wei = int(tx.get("value", 0))
        value_eth = Decimal(value_wei) / Decimal(10**18)
        input_data = tx.get("input", "0x")

        event_data = {
            "tx_hash": tx.get("hash"),
            "from_address": from_addr,
            "to_address": to_addr,
            "value_wei": value_wei,
            "value_eth": float(value_eth),
            "gas_price": tx.get("gasPrice"),
            "max_fee_per_gas": tx.get("maxFeePerGas"),
            "max_priority_fee": tx.get("maxPriorityFeePerGas"),
            "nonce": tx.get("nonce"),
            "pending": True,
        }

        await self._emit("pending_tx", event_data)

        # Large transfer detection
        if value_eth >= self._large_threshold:
            await self._emit("pending_large_transfer", event_data)

        # Contract interaction detection (input data beyond just a transfer)
        if input_data and len(input_data) > 10:
            method_selector = input_data[:10]
            await self._emit(
                "pending_contract_interaction",
                {**event_data, "method_selector": method_selector},
            )

    @property
    def watched_count(self) -> int:
        """Number of addresses being watched in the mempool."""
        return len(self._watched_addresses)

    @property
    def seen_count(self) -> int:
        """Number of unique transaction hashes seen."""
        return len(self._seen_hashes)
