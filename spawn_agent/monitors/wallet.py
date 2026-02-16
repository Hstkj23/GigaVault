"""
Wallet monitor for tracking EOA (Externally Owned Account) activity.

Monitors incoming and outgoing transactions, balance changes,
and token transfers for a specific wallet address.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any, Optional

from spawn_agent.monitors.base import BaseMonitor

logger = logging.getLogger(__name__)

# Threshold in ETH for "large transfer" events
DEFAULT_LARGE_TRANSFER_THRESHOLD = Decimal("10.0")


class WalletMonitor(BaseMonitor):
    """
    Monitors a single wallet address for on-chain activity.

    Tracks:
        - Incoming and outgoing ETH transfers
        - ERC-20 token transfers (via Transfer event logs)
        - Balance changes exceeding configurable thresholds
        - Interaction with known contract addresses

    Events emitted:
        - ``transfer_in``: ETH received by the wallet
        - ``transfer_out``: ETH sent from the wallet
        - ``token_transfer``: ERC-20 token movement
        - ``large_transfer``: Transfer exceeding the configured threshold
        - ``new_interaction``: First-time interaction with a contract

    Args:
        address: Wallet address to monitor.
        label: Human-readable label.
        provider: RPC provider instance.
        options: Configuration overrides.
    """

    def __init__(
        self,
        address: str,
        label: Optional[str] = None,
        provider: Any = None,
        options: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(address, label, provider, options)
        self._large_threshold = Decimal(
            str(self.options.get("large_transfer_threshold", DEFAULT_LARGE_TRANSFER_THRESHOLD))
        )
        self._known_interactions: set[str] = set()
        self._last_balance: Optional[Decimal] = None
        self._last_nonce: Optional[int] = None

    async def _run(self) -> None:
        """Main polling loop for wallet monitoring."""
        logger.info("Wallet monitor started for %s (%s)", self.label, self.address)

        # Initialize baseline state
        await self._initialize_state()

        while self._running:
            try:
                await self._poll_cycle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "Error in wallet monitor for %s: %s", self.address, exc
                )
            await asyncio.sleep(self._poll_interval)

    async def _initialize_state(self) -> None:
        """Capture initial wallet state for comparison."""
        if self.provider is None:
            return

        try:
            self._last_balance = await self.provider.get_balance(self.address)
            self._last_nonce = await self.provider.get_transaction_count(self.address)
            self._last_block = await self._get_current_block()
        except Exception as exc:
            logger.warning("Failed to initialize state for %s: %s", self.address, exc)

    async def _poll_cycle(self) -> None:
        """Execute one polling cycle: check for new transactions and balance changes."""
        if self.provider is None:
            return

        current_block = await self._get_current_block()
        if self._last_block is None:
            self._last_block = current_block
            return

        if current_block <= self._last_block:
            return

        # Fetch transactions in the new block range
        transactions = await self._fetch_transactions(
            self._last_block + 1, current_block
        )

        for tx in transactions:
            await self._process_transaction(tx)

        # Check for token transfers via logs
        token_transfers = await self._fetch_token_transfers(
            self._last_block + 1, current_block
        )

        for transfer in token_transfers:
            await self._process_token_transfer(transfer)

        # Update balance tracking
        await self._check_balance_change()

        self._last_block = current_block

    async def _fetch_transactions(
        self, from_block: int, to_block: int
    ) -> list[dict[str, Any]]:
        """Fetch transactions involving this address in the given block range."""
        try:
            return await self.provider.get_transactions(
                address=self.address,
                from_block=from_block,
                to_block=to_block,
            )
        except Exception as exc:
            logger.debug("Failed to fetch transactions: %s", exc)
            return []

    async def _fetch_token_transfers(
        self, from_block: int, to_block: int
    ) -> list[dict[str, Any]]:
        """Fetch ERC-20 Transfer event logs for this address."""
        # ERC-20 Transfer(address,address,uint256) topic
        transfer_topic = (
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        )

        try:
            logs = await self.provider.get_logs(
                from_block=from_block,
                to_block=to_block,
                topics=[transfer_topic],
                address_filter=self.address,
            )
            return self._parse_transfer_logs(logs)
        except Exception as exc:
            logger.debug("Failed to fetch token transfers: %s", exc)
            return []

    def _parse_transfer_logs(self, logs: list[dict]) -> list[dict[str, Any]]:
        """Parse raw ERC-20 Transfer event logs into structured data."""
        transfers = []
        for log in logs:
            topics = log.get("topics", [])
            if len(topics) < 3:
                continue

            from_addr = "0x" + topics[1][-40:]
            to_addr = "0x" + topics[2][-40:]
            raw_value = int(log.get("data", "0x0"), 16)
            token_address = log.get("address", "").lower()

            transfers.append(
                {
                    "from": from_addr.lower(),
                    "to": to_addr.lower(),
                    "value_raw": raw_value,
                    "token_address": token_address,
                    "block_number": log.get("blockNumber"),
                    "tx_hash": log.get("transactionHash"),
                }
            )
        return transfers

    async def _process_transaction(self, tx: dict[str, Any]) -> None:
        """Process a single transaction and emit appropriate events."""
        from_addr = tx.get("from", "").lower()
        to_addr = tx.get("to", "").lower()
        value_wei = int(tx.get("value", 0))
        value_eth = Decimal(value_wei) / Decimal(10**18)

        event_data = {
            "tx_hash": tx.get("hash"),
            "from_address": from_addr,
            "to_address": to_addr,
            "value_wei": value_wei,
            "value_eth": float(value_eth),
            "block_number": tx.get("blockNumber"),
            "gas_used": tx.get("gasUsed"),
        }

        # Determine direction
        if from_addr == self.address:
            await self._emit("transfer_out", event_data)

            # Track new interactions
            if to_addr and to_addr not in self._known_interactions:
                self._known_interactions.add(to_addr)
                await self._emit("new_interaction", {
                    **event_data,
                    "interacted_address": to_addr,
                })
        elif to_addr == self.address:
            await self._emit("transfer_in", event_data)

        # Check for large transfer
        if value_eth >= self._large_threshold:
            await self._emit("large_transfer", event_data)

    async def _process_token_transfer(self, transfer: dict[str, Any]) -> None:
        """Process a token transfer event."""
        await self._emit("token_transfer", transfer)

    async def _check_balance_change(self) -> None:
        """Check if the wallet balance has changed significantly."""
        try:
            current_balance = await self.provider.get_balance(self.address)
        except Exception:
            return

        if self._last_balance is not None and current_balance != self._last_balance:
            delta = current_balance - self._last_balance
            await self._emit(
                "balance_change",
                {
                    "previous_balance": float(self._last_balance),
                    "current_balance": float(current_balance),
                    "delta": float(delta),
                },
            )

        self._last_balance = current_balance
