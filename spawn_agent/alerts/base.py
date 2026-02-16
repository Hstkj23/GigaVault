"""
Base alert handler interface.

All notification handlers implement this base class.
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """Structured alert payload."""

    title: str
    message: str
    severity: str = "info"  # info, warning, critical
    source: str = ""
    address: Optional[str] = None
    tx_hash: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "message": self.message,
            "severity": self.severity,
            "source": self.source,
            "address": self.address,
            "tx_hash": self.tx_hash,
            "metadata": self.metadata,
        }

    def format_text(self) -> str:
        """Format as plain text for notification."""
        parts = [f"[{self.severity.upper()}] {self.title}", self.message]
        if self.address:
            parts.append(f"Address: {self.address}")
        if self.tx_hash:
            parts.append(f"TX: {self.tx_hash}")
        return "\n".join(parts)

    def format_markdown(self) -> str:
        """Format as Markdown for rich notifications."""
        severity_emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "critical": "🚨",
        }
        emoji = severity_emoji.get(self.severity, "📌")
        parts = [f"{emoji} **{self.title}**", "", self.message]
        if self.address:
            parts.append(f"\n**Address:** `{self.address}`")
        if self.tx_hash:
            parts.append(f"**TX:** `{self.tx_hash}`")
        return "\n".join(parts)


class AlertHandler(abc.ABC):
    """
    Abstract base class for alert notification handlers.

    Subclasses must implement the ``send`` method to deliver
    alerts through their specific channel.
    """

    def __init__(self, name: str = "unnamed") -> None:
        self.name = name
        self._sent_count = 0
        self._error_count = 0

    @abc.abstractmethod
    async def send(self, alert: Alert) -> bool:
        """
        Send an alert notification.

        Returns True if the alert was sent successfully.
        """
        ...

    async def safe_send(self, alert: Alert) -> bool:
        """Send with exception handling."""
        try:
            result = await self.send(alert)
            if result:
                self._sent_count += 1
            return result
        except Exception as exc:
            self._error_count += 1
            logger.error(
                "Alert handler '%s' failed: %s", self.name, exc
            )
            return False

    @property
    def stats(self) -> dict[str, int]:
        return {"sent": self._sent_count, "errors": self._error_count}
