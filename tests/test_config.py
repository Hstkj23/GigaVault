"""Tests for configuration management."""

import os
from unittest.mock import patch

import pytest

from spawn_agent.utils.config import AgentConfig


class TestAgentConfig:
    """Test configuration loading and validation."""

    def test_default_config(self):
        config = AgentConfig()
        assert config.chain_id == 1
        assert config.max_workers == 1000
        assert config.log_level == "INFO"
        assert config.poll_interval == 2.0

    def test_from_dict(self, sample_config_dict):
        config = AgentConfig.from_dict(sample_config_dict)
        assert config.rpc_url == "https://eth-mainnet.example.com/v2/test-key"
        assert config.chain_id == 1
        assert config.max_connections == 25
        assert config.max_workers == 500
        assert config.supervisor_restart_limit == 3
        assert config.log_level == "DEBUG"

    def test_from_dict_empty(self):
        config = AgentConfig.from_dict({})
        assert config.chain_id == 1
        assert config.rpc_url == ""

    @patch.dict(os.environ, {"SPAWN_AGENT_RPC_URL": "https://override.example.com"})
    def test_env_override(self):
        config = AgentConfig(rpc_url="https://original.example.com")
        assert config.rpc_url == "https://override.example.com"

    @patch.dict(os.environ, {"SPAWN_AGENT_CHAIN_ID": "137"})
    def test_env_override_int(self):
        config = AgentConfig()
        assert config.chain_id == 137

    def test_to_dict_masks_sensitive(self):
        config = AgentConfig(
            rpc_url="https://eth.example.com/v2/my-secret-api-key",
            telegram_bot_token="1234567890:ABCdefGHIjklmNOPqrstUVwxyz",
        )
        d = config.to_dict()
        # Sensitive values should be partially masked
        assert "***" in d["telegram_bot_token"]

    def test_from_dict_with_alerts(self):
        data = {
            "provider": {"rpc_url": "https://test.com"},
            "alerts": {
                "discord": {
                    "enabled": True,
                    "webhook_url": "https://discord.com/webhook/123",
                }
            },
        }
        config = AgentConfig.from_dict(data)
        assert config.discord_webhook_url == "https://discord.com/webhook/123"
