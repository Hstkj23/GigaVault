"""
JSON-RPC provider for EVM-compatible blockchains.

Handles connection pooling, request batching, rate limiting,
and automatic retry with exponential backoff.
"""

from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)


class RPCError(Exception):
    """Error from the RPC provider."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        super().__init__(f"RPC Error {code}: {message}")


class RPCProvider:
    """
    Async JSON-RPC client with connection pooling and retry logic.

    Supports:
        - Connection pooling via aiohttp
        - Automatic retry with exponential backoff
        - Request batching for bulk queries
        - Rate limiting to respect provider quotas

    Args:
        url: JSON-RPC endpoint URL.
        chain_id: EVM chain ID.
        max_connections: Maximum concurrent connections.
        timeout: Request timeout in seconds.
        max_retries: Maximum retry attempts on failure.
        rate_limit: Maximum requests per second (0 = unlimited).
    """

    def __init__(
        self,
        url: str,
        chain_id: int = 1,
        max_connections: int = 50,
        timeout: float = 30.0,
        max_retries: int = 3,
        rate_limit: int = 0,
    ) -> None:
        self.url = url
        self.chain_id = chain_id
        self.max_connections = max_connections
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limit = rate_limit

        self._session: Optional[aiohttp.ClientSession] = None
        self._request_id = 0
        self._request_count = 0
        self._last_request_time = 0.0
        self._semaphore = asyncio.Semaphore(max_connections)

    async def connect(self) -> None:
        """Initialize the HTTP connection pool."""
        connector = aiohttp.TCPConnector(
            limit=self.max_connections,
            limit_per_host=self.max_connections,
            ttl_dns_cache=300,
        )
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        logger.info("RPC provider connected to %s (chain %d)", self.url, self.chain_id)

    async def close(self) -> None:
        """Close the connection pool."""
        if self._session:
            await self._session.close()
            self._session = None

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        """Execute a single JSON-RPC call with retry logic."""
        if self._session is None:
            raise RuntimeError("Provider not connected. Call connect() first.")

        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or [],
            "id": self._request_id,
        }

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            # Rate limiting
            if self.rate_limit > 0:
                elapsed = time.monotonic() - self._last_request_time
                min_interval = 1.0 / self.rate_limit
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)

            async with self._semaphore:
                try:
                    self._last_request_time = time.monotonic()
                    self._request_count += 1

                    async with self._session.post(
                        self.url, json=payload
                    ) as response:
                        if response.status == 429:
                            # Rate limited — back off
                            backoff = 2 ** attempt
                            logger.warning(
                                "Rate limited. Backing off %ds", backoff
                            )
                            await asyncio.sleep(backoff)
                            continue

                        response.raise_for_status()
                        data = await response.json()

                        if "error" in data:
                            err = data["error"]
                            raise RPCError(
                                err.get("code", -1), err.get("message", "Unknown")
                            )

                        return data.get("result")

                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    last_error = exc
                    backoff = min(2 ** attempt, 10)
                    logger.warning(
                        "RPC request failed (attempt %d/%d): %s",
                        attempt + 1,
                        self.max_retries + 1,
                        exc,
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(backoff)

        raise ConnectionError(
            f"RPC call {method} failed after {self.max_retries + 1} attempts: "
            f"{last_error}"
        )

    async def batch_call(
        self, calls: list[tuple[str, list[Any] | None]]
    ) -> list[Any]:
        """
        Execute multiple RPC calls in a single batch request.

        Args:
            calls: List of (method, params) tuples.

        Returns:
            List of results in the same order as the input calls.
        """
        if self._session is None:
            raise RuntimeError("Provider not connected.")

        payloads = []
        for method, params in calls:
            self._request_id += 1
            payloads.append(
                {
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": params or [],
                    "id": self._request_id,
                }
            )

        async with self._semaphore:
            async with self._session.post(self.url, json=payloads) as response:
                response.raise_for_status()
                results = await response.json()

        # Sort results by ID to match input order
        result_map = {r["id"]: r.get("result") for r in results}
        return [result_map.get(p["id"]) for p in payloads]

    async def get_block_number(self) -> int:
        """Get the current block number."""
        result = await self._call("eth_blockNumber")
        return int(result, 16)

    async def get_balance(self, address: str) -> Decimal:
        """Get the ETH balance of an address in ETH."""
        result = await self._call("eth_getBalance", [address, "latest"])
        wei = int(result, 16)
        return Decimal(wei) / Decimal(10**18)

    async def get_transaction_count(self, address: str) -> int:
        """Get the nonce (transaction count) for an address."""
        result = await self._call("eth_getTransactionCount", [address, "latest"])
        return int(result, 16)

    async def get_transaction(self, tx_hash: str) -> Optional[dict[str, Any]]:
        """Get transaction details by hash."""
        result = await self._call("eth_getTransactionByHash", [tx_hash])
        if result:
            return self._normalize_transaction(result)
        return None

    async def get_block(
        self, block_number: int, full_transactions: bool = False
    ) -> Optional[dict[str, Any]]:
        """Get block data by number."""
        hex_block = hex(block_number)
        return await self._call("eth_getBlockByNumber", [hex_block, full_transactions])

    async def get_transactions(
        self,
        address: str,
        from_block: int,
        to_block: int,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        """
        Get transactions for an address in a block range.

        This uses eth_getLogs with internal transaction tracing when available,
        falling back to block-by-block scanning.
        """
        transactions: list[dict[str, Any]] = []

        # Scan blocks in the range for transactions involving this address
        for block_num in range(from_block, to_block + 1):
            block = await self.get_block(block_num, full_transactions=True)
            if block is None:
                continue

            for tx in block.get("transactions", []):
                if isinstance(tx, str):
                    continue  # Not full transaction data

                from_addr = tx.get("from", "").lower()
                to_addr = tx.get("to", "").lower()
                addr = address.lower()

                if direction == "incoming" and to_addr != addr:
                    continue
                if direction == "outgoing" and from_addr != addr:
                    continue
                if direction == "both" and from_addr != addr and to_addr != addr:
                    continue

                transactions.append(self._normalize_transaction(tx))

        return transactions

    async def get_logs(
        self,
        from_block: int,
        to_block: int,
        topics: Optional[list] = None,
        contract_address: Optional[str] = None,
        address_filter: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fetch event logs with topic and address filters."""
        params: dict[str, Any] = {
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
        }

        if contract_address:
            params["address"] = contract_address
        if topics:
            params["topics"] = topics

        result = await self._call("eth_getLogs", [params])

        if address_filter:
            address_filter = address_filter.lower()
            result = [
                log
                for log in (result or [])
                if self._log_involves_address(log, address_filter)
            ]

        return result or []

    async def get_code(self, address: str) -> str:
        """Get the bytecode at an address (empty for EOAs)."""
        return await self._call("eth_getCode", [address, "latest"])

    async def is_contract(self, address: str) -> bool:
        """Check if an address is a smart contract."""
        code = await self.get_code(address)
        return code is not None and code != "0x" and len(code) > 2

    @staticmethod
    def _normalize_transaction(tx: dict) -> dict[str, Any]:
        """Normalize transaction fields to consistent types."""
        return {
            "hash": tx.get("hash"),
            "from": tx.get("from", "").lower(),
            "to": (tx.get("to") or "").lower(),
            "value": int(tx.get("value", "0x0"), 16) if isinstance(tx.get("value"), str) else tx.get("value", 0),
            "blockNumber": int(tx.get("blockNumber", "0x0"), 16) if isinstance(tx.get("blockNumber"), str) else tx.get("blockNumber", 0),
            "gasUsed": tx.get("gasUsed"),
            "gasPrice": tx.get("gasPrice"),
            "maxFeePerGas": tx.get("maxFeePerGas"),
            "maxPriorityFeePerGas": tx.get("maxPriorityFeePerGas"),
            "input": tx.get("input", "0x"),
            "nonce": int(tx.get("nonce", "0x0"), 16) if isinstance(tx.get("nonce"), str) else tx.get("nonce", 0),
        }

    @staticmethod
    def _log_involves_address(log: dict, address: str) -> bool:
        """Check if a log entry involves a specific address."""
        topics = log.get("topics", [])
        for topic in topics:
            if topic and address[2:] in topic.lower():
                return True
        return False

    @property
    def request_count(self) -> int:
        return self._request_count

    def __repr__(self) -> str:
        return f"<RPCProvider url={self.url} chain={self.chain_id} requests={self._request_count}>"
