"""Tests for the SpawnAgent core agent module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spawn_agent.core.agent import SpawnAgent
from spawn_agent.utils.config import AgentConfig


class TestSpawnAgentInit:
    """Test agent initialization."""

    def test_create_with_defaults(self):
        agent = SpawnAgent.create(
            rpc_url="https://eth.example.com",
            chain_id=1,
        )
        assert agent.config.rpc_url == "https://eth.example.com"
        assert agent.config.chain_id == 1
        assert agent.monitor_count == 0
        assert not agent.is_running

    def test_create_with_custom_settings(self):
        agent = SpawnAgent.create(
            rpc_url="https://eth.example.com",
            chain_id=137,
            max_workers=500,
            log_level="DEBUG",
        )
        assert agent.config.chain_id == 137
        assert agent.config.max_workers == 500
        assert agent.config.log_level == "DEBUG"

    def test_repr(self):
        agent = SpawnAgent.create(rpc_url="https://eth.example.com")
        r = repr(agent)
        assert "SpawnAgent" in r
        assert "stopped" in r
        assert "monitors=0" in r


class TestSpawnAgentWatch:
    """Test address monitoring registration."""

    def test_watch_wallet(self):
        agent = SpawnAgent.create(rpc_url="https://eth.example.com")
        monitor_id = agent.watch(
            "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68",
            label="Test Wallet",
        )
        assert monitor_id == "0x742d35cc6634c0532925a3b844bc9e7595f2bd68"
        assert agent.monitor_count == 1

    def test_watch_contract(self):
        agent = SpawnAgent.create(rpc_url="https://eth.example.com")
        agent.watch(
            "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            label="USDT",
            monitor_type="contract",
        )
        assert agent.monitor_count == 1

    def test_watch_duplicate_address(self):
        agent = SpawnAgent.create(rpc_url="https://eth.example.com")
        addr = "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68"
        agent.watch(addr)
        agent.watch(addr)  # Should not add again
        assert agent.monitor_count == 1

    def test_watch_normalizes_address(self):
        agent = SpawnAgent.create(rpc_url="https://eth.example.com")
        agent.watch("0xABCDEF1234567890abcdef1234567890ABCDEF12")
        assert agent.monitor_count == 1

    def test_watch_max_workers_exceeded(self):
        agent = SpawnAgent.create(
            rpc_url="https://eth.example.com", max_workers=2
        )
        agent.watch("0x1111111111111111111111111111111111111111")
        agent.watch("0x2222222222222222222222222222222222222222")
        with pytest.raises(RuntimeError, match="Maximum worker count"):
            agent.watch("0x3333333333333333333333333333333333333333")

    def test_unwatch(self):
        agent = SpawnAgent.create(rpc_url="https://eth.example.com")
        addr = "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68"
        agent.watch(addr)
        assert agent.monitor_count == 1
        result = agent.unwatch(addr)
        assert result is True
        assert agent.monitor_count == 0

    def test_unwatch_unknown_address(self):
        agent = SpawnAgent.create(rpc_url="https://eth.example.com")
        result = agent.unwatch("0x0000000000000000000000000000000000000000")
        assert result is False


class TestSpawnAgentEvents:
    """Test event handler registration."""

    def test_on_decorator(self):
        agent = SpawnAgent.create(rpc_url="https://eth.example.com")

        @agent.on("large_transfer")
        async def handler(event):
            pass

        assert "large_transfer" in agent._event_handlers
        assert len(agent._event_handlers["large_transfer"]) == 1

    def test_add_handler(self):
        agent = SpawnAgent.create(rpc_url="https://eth.example.com")

        async def handler(event):
            pass

        agent.add_handler("transfer_in", handler)
        assert "transfer_in" in agent._event_handlers

    def test_multiple_handlers_same_event(self):
        agent = SpawnAgent.create(rpc_url="https://eth.example.com")

        @agent.on("transfer_in")
        async def handler1(event):
            pass

        @agent.on("transfer_in")
        async def handler2(event):
            pass

        assert len(agent._event_handlers["transfer_in"]) == 2

    @pytest.mark.asyncio
    async def test_dispatch_event(self):
        agent = SpawnAgent.create(rpc_url="https://eth.example.com")
        received = []

        @agent.on("test_event")
        async def handler(event):
            received.append(event)

        await agent._dispatch_event({"type": "test_event", "data": "hello"})
        assert len(received) == 1
        assert received[0]["data"] == "hello"

    @pytest.mark.asyncio
    async def test_wildcard_handler(self):
        agent = SpawnAgent.create(rpc_url="https://eth.example.com")
        received = []

        @agent.on("*")
        async def catch_all(event):
            received.append(event)

        await agent._dispatch_event({"type": "any_event"})
        assert len(received) == 1
