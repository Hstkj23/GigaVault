"""
Configuration management for SpawnAgent.

Supports loading from YAML files, environment variables, and
programmatic overrides with sensible defaults.
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """
    Configuration for a SpawnAgent instance.

    All settings can be overridden via environment variables prefixed
    with ``SPAWN_AGENT_``. For example, ``SPAWN_AGENT_RPC_URL`` overrides
    the ``rpc_url`` setting.
    """

    # Provider settings
    rpc_url: str = ""
    ws_url: str = ""
    chain_id: int = 1
    max_connections: int = 50
    rpc_timeout: float = 30.0
    ws_reconnect_interval: float = 5.0

    # Monitoring settings
    poll_interval: float = 2.0
    max_workers: int = 1000
    supervisor_restart_limit: int = 5
    supervisor_restart_window: float = 60.0

    # Alert settings
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""
    webhook_url: str = ""

    # Analysis settings
    anomaly_volume_window: float = 3600.0
    anomaly_volume_threshold: float = 5.0
    anomaly_rapid_tx_threshold: int = 10
    pattern_window_size: int = 5000
    pattern_min_confidence: float = 0.5

    # General
    log_level: str = "INFO"
    data_dir: str = "./data"

    def __post_init__(self) -> None:
        """Apply environment variable overrides."""
        env_map = {
            "SPAWN_AGENT_RPC_URL": "rpc_url",
            "SPAWN_AGENT_WS_URL": "ws_url",
            "SPAWN_AGENT_CHAIN_ID": "chain_id",
            "SPAWN_AGENT_MAX_WORKERS": "max_workers",
            "SPAWN_AGENT_LOG_LEVEL": "log_level",
            "SPAWN_AGENT_TELEGRAM_TOKEN": "telegram_bot_token",
            "SPAWN_AGENT_TELEGRAM_CHAT": "telegram_chat_id",
            "SPAWN_AGENT_DISCORD_WEBHOOK": "discord_webhook_url",
            "SPAWN_AGENT_WEBHOOK_URL": "webhook_url",
            "ETH_RPC_URL": "rpc_url",  # Common convention fallback
        }

        for env_var, attr in env_map.items():
            value = os.environ.get(env_var)
            if value is not None:
                current = getattr(self, attr)
                if isinstance(current, int):
                    setattr(self, attr, int(value))
                elif isinstance(current, float):
                    setattr(self, attr, float(value))
                else:
                    setattr(self, attr, value)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentConfig:
        """Create configuration from a nested dictionary (YAML structure)."""
        flat: dict[str, Any] = {}

        # Flatten nested config structure
        provider = data.get("provider", {})
        flat["rpc_url"] = provider.get("rpc_url", "")
        flat["ws_url"] = provider.get("ws_url", "")
        flat["chain_id"] = provider.get("chain_id", 1)
        flat["max_connections"] = provider.get("max_connections", 50)
        flat["rpc_timeout"] = provider.get("timeout", 30.0)

        monitoring = data.get("monitoring", {})
        flat["poll_interval"] = monitoring.get("poll_interval", 2.0)
        flat["max_workers"] = monitoring.get("max_workers", 1000)
        flat["supervisor_restart_limit"] = monitoring.get(
            "supervisor_restart_limit", 5
        )

        alerts = data.get("alerts", {})
        telegram = alerts.get("telegram", {})
        if telegram.get("enabled"):
            flat["telegram_bot_token"] = _resolve_env(
                telegram.get("bot_token", "")
            )
            flat["telegram_chat_id"] = _resolve_env(
                telegram.get("chat_id", "")
            )

        discord = alerts.get("discord", {})
        if discord.get("enabled"):
            flat["discord_webhook_url"] = _resolve_env(
                discord.get("webhook_url", "")
            )

        analysis = data.get("analysis", {})
        flat["anomaly_volume_window"] = analysis.get("volume_window", 3600.0)
        flat["anomaly_volume_threshold"] = analysis.get("volume_threshold", 5.0)

        flat["log_level"] = data.get("log_level", "INFO")
        flat["data_dir"] = data.get("data_dir", "./data")

        # Filter to only valid fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in flat.items() if k in valid_fields}

        return cls(**filtered)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary (masking sensitive values)."""
        import dataclasses

        result = dataclasses.asdict(self)
        # Mask sensitive fields
        for key in ["telegram_bot_token", "discord_webhook_url", "webhook_url"]:
            if result.get(key):
                result[key] = result[key][:8] + "***"
        if result.get("rpc_url"):
            # Mask API key portion of RPC URL
            url = result["rpc_url"]
            if "/" in url:
                parts = url.rsplit("/", 1)
                if len(parts[1]) > 8:
                    result["rpc_url"] = parts[0] + "/" + parts[1][:8] + "***"
        return result


def _resolve_env(value: str) -> str:
    """Resolve ${ENV_VAR} references in configuration values."""
    if value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1]
        return os.environ.get(env_name, "")
    return value


def load_config(path: str | Path) -> AgentConfig:
    """Load configuration from a YAML file."""
    import yaml

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    return AgentConfig.from_dict(raw or {})
