"""Discord alert handler via webhooks."""

from __future__ import annotations

import logging
from typing import Any, Optional

import aiohttp

from spawn_agent.alerts.base import Alert, AlertHandler

logger = logging.getLogger(__name__)

SEVERITY_COLORS = {
    "info": 0x3498DB,       # Blue
    "warning": 0xF39C12,    # Orange
    "critical": 0xE74C3C,   # Red
}


class DiscordAlertHandler(AlertHandler):
    """
    Sends alert notifications via Discord webhooks.

    Uses Discord embeds for rich formatting with severity-based colors.

    Args:
        webhook_url: Discord webhook URL.
        username: Display name for the webhook.
        avatar_url: Avatar URL for the webhook.
    """

    def __init__(
        self,
        webhook_url: str,
        username: str = "SpawnAgent",
        avatar_url: Optional[str] = None,
    ) -> None:
        super().__init__(name="discord")
        self.webhook_url = webhook_url
        self.username = username
        self.avatar_url = avatar_url
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def send(self, alert: Alert) -> bool:
        """Send an alert as a Discord embed via webhook."""
        session = await self._ensure_session()

        embed = self._build_embed(alert)
        payload: dict[str, Any] = {
            "username": self.username,
            "embeds": [embed],
        }
        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url

        async with session.post(self.webhook_url, json=payload) as response:
            if response.status in (200, 204):
                return True
            else:
                body = await response.text()
                logger.error(
                    "Discord webhook error %d: %s", response.status, body
                )
                return False

    def _build_embed(self, alert: Alert) -> dict[str, Any]:
        """Build a Discord embed from an alert."""
        color = SEVERITY_COLORS.get(alert.severity, 0x95A5A6)

        embed: dict[str, Any] = {
            "title": alert.title,
            "description": alert.message,
            "color": color,
        }

        fields = []
        if alert.address:
            fields.append(
                {"name": "Address", "value": f"`{alert.address}`", "inline": True}
            )
        if alert.tx_hash:
            fields.append(
                {"name": "Transaction", "value": f"`{alert.tx_hash}`", "inline": True}
            )
        if alert.metadata:
            for key, value in list(alert.metadata.items())[:5]:
                fields.append(
                    {"name": key, "value": str(value), "inline": True}
                )

        if fields:
            embed["fields"] = fields

        embed["footer"] = {"text": f"SpawnAgent • {alert.severity.upper()}"}
        return embed

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
