"""Generic webhook alert handler."""

from __future__ import annotations

import logging
from typing import Any, Optional

import aiohttp

from spawn_agent.alerts.base import Alert, AlertHandler

logger = logging.getLogger(__name__)


class WebhookAlertHandler(AlertHandler):
    """
    Sends alerts to a generic HTTP webhook endpoint.

    Posts the alert as JSON to the configured URL. Supports
    custom headers for authentication and routing.

    Args:
        url: Webhook endpoint URL.
        headers: Optional HTTP headers (e.g., authorization).
        method: HTTP method (POST or PUT).
    """

    def __init__(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
        method: str = "POST",
    ) -> None:
        super().__init__(name="webhook")
        self.url = url
        self.headers = headers or {}
        self.method = method.upper()
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Content-Type": "application/json", **self.headers}
            )
        return self._session

    async def send(self, alert: Alert) -> bool:
        """Send the alert as a JSON POST/PUT to the webhook."""
        session = await self._ensure_session()
        payload = alert.to_dict()

        if self.method == "PUT":
            send_func = session.put
        else:
            send_func = session.post

        async with send_func(self.url, json=payload) as response:
            if response.status < 400:
                return True
            else:
                body = await response.text()
                logger.error(
                    "Webhook error %d: %s", response.status, body
                )
                return False

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
