"""
Type definitions and data structures for SpawnAgent.

Provides typed dataclasses for common domain objects used
across the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class Chain(Enum):
    """Supported blockchain networks."""

    ETHEREUM = 1
    GOERLI = 5
    POLYGON = 137
    ARBITRUM = 42161
    OPTIMISM = 10
    BASE = 8453
    BSC = 56
    AVALANCHE = 43114


class TransactionDirection(Enum):
    """Direction of a transaction relative to a monitored address."""

    INCOMING = "incoming"
    OUTGOING = "outgoing"
    INTERNAL = "internal"


@dataclass
class Address:
    """A blockchain address with optional metadata."""

    address: str
    label: Optional[str] = None
    is_contract: bool = False
    chain: Chain = Chain.ETHEREUM
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.address = self.address.lower().strip()

    def __hash__(self):
        return hash(self.address)

    def __eq__(self, other):
        if isinstance(other, Address):
            return self.address == other.address
        if isinstance(other, str):
            return self.address == other.lower()
        return False

    @property
    def short(self) -> str:
        """Shortened address for display (0x1234...abcd)."""
        if len(self.address) >= 42:
            return f"{self.address[:6]}...{self.address[-4:]}"
        return self.address


@dataclass
class Transaction:
    """A normalized blockchain transaction."""

    hash: str
    from_address: str
    to_address: str
    value_wei: int
    block_number: int
    gas_used: Optional[int] = None
    gas_price: Optional[int] = None
    input_data: str = "0x"
    timestamp: Optional[int] = None
    nonce: int = 0
    status: bool = True

    @property
    def value_eth(self) -> Decimal:
        return Decimal(self.value_wei) / Decimal(10**18)

    @property
    def value_gwei(self) -> Decimal:
        return Decimal(self.value_wei) / Decimal(10**9)

    @property
    def method_selector(self) -> str:
        if len(self.input_data) >= 10:
            return self.input_data[:10]
        return "0x"

    def to_dict(self) -> dict[str, Any]:
        return {
            "hash": self.hash,
            "from": self.from_address,
            "to": self.to_address,
            "value_wei": self.value_wei,
            "value_eth": float(self.value_eth),
            "block_number": self.block_number,
            "gas_used": self.gas_used,
            "gas_price": self.gas_price,
            "input": self.input_data,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
        }


@dataclass
class TokenTransfer:
    """An ERC-20 token transfer event."""

    token_address: str
    from_address: str
    to_address: str
    value_raw: int
    decimals: int = 18
    symbol: Optional[str] = None
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None

    @property
    def value_normalized(self) -> Decimal:
        return Decimal(self.value_raw) / Decimal(10**self.decimals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token_address,
            "from": self.from_address,
            "to": self.to_address,
            "value_raw": self.value_raw,
            "value": float(self.value_normalized),
            "symbol": self.symbol,
            "tx_hash": self.tx_hash,
            "block_number": self.block_number,
        }


@dataclass
class MonitorConfig:
    """Configuration for a single monitor instance."""

    address: str
    label: Optional[str] = None
    monitor_type: str = "wallet"
    poll_interval: float = 2.0
    large_transfer_threshold: Decimal = Decimal("10.0")
    alert_channels: list[str] = field(default_factory=list)
    custom_options: dict[str, Any] = field(default_factory=dict)
