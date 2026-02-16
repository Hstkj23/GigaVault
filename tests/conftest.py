"""Shared test fixtures for the SpawnAgent test suite."""

import asyncio
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_provider():
    """Create a mock RPC provider."""
    provider = AsyncMock()
    provider.get_block_number = AsyncMock(return_value=18000000)
    provider.get_balance = AsyncMock(return_value=1.5)
    provider.get_transaction_count = AsyncMock(return_value=42)
    provider.get_transactions = AsyncMock(return_value=[])
    provider.get_logs = AsyncMock(return_value=[])
    provider.get_transaction = AsyncMock(return_value=None)
    provider.connect = AsyncMock()
    provider.close = AsyncMock()
    return provider


@pytest.fixture
def sample_transaction() -> dict[str, Any]:
    """Create a sample transaction for testing."""
    return {
        "hash": "0xabc123def456789",
        "from": "0x1111111111111111111111111111111111111111",
        "to": "0x2222222222222222222222222222222222222222",
        "value": 1000000000000000000,  # 1 ETH in wei
        "blockNumber": 18000001,
        "gasUsed": 21000,
        "gasPrice": 30000000000,
        "input": "0x",
        "nonce": 5,
    }


@pytest.fixture
def sample_token_transfer() -> dict[str, Any]:
    """Create a sample ERC-20 transfer event for testing."""
    return {
        "from": "0x1111111111111111111111111111111111111111",
        "to": "0x2222222222222222222222222222222222222222",
        "value_raw": 1000000000000000000,
        "token_address": "0x3333333333333333333333333333333333333333",
        "block_number": 18000001,
        "tx_hash": "0xdef456abc789",
    }


@pytest.fixture
def sample_config_dict() -> dict[str, Any]:
    """Create a sample configuration dictionary."""
    return {
        "provider": {
            "rpc_url": "https://eth-mainnet.example.com/v2/test-key",
            "chain_id": 1,
            "max_connections": 25,
        },
        "monitoring": {
            "poll_interval": 2.0,
            "max_workers": 500,
            "supervisor_restart_limit": 3,
        },
        "alerts": {
            "telegram": {
                "enabled": False,
            }
        },
        "log_level": "DEBUG",
    }
