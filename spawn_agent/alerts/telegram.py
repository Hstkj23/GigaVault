"""Telegram alert handler."""

from __future__ import annotations

import logging
from typing import Optional

import aiohttp

from spawn_agent.alerts.base import Alert, AlertHandler

logger = logging.getLogger(__name__)


class TelegramAlertHandler(AlertHandler):
    """
    Sends alert notifications via the Telegram Bot API.

    Args:
        bot_token: Telegram bot API token.
        chat_id: Target chat/group/channel ID.
        parse_mode: Message parse mode (Markdown or HTML).
    """

    API_BASE = "https://api.telegram.org/bot{token}"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        parse_mode: str = "Markdown",
    ) -> None:
        super().__init__(name="telegram")
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.parse_mode = parse_mode
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def send(self, alert: Alert) -> bool:
        """Send an alert message via Telegram."""
        session = await self._ensure_session()
        url = f"{self.API_BASE.format(token=self.bot_token)}/sendMessage"

        text = alert.format_markdown()

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": self.parse_mode,
            "disable_web_page_preview": True,
        }

        async with session.post(url, json=payload) as response:
            if response.status == 200:
                return True
            else:
                body = await response.text()
                logger.error(
                    "Telegram API error %d: %s", response.status, body
                )
                return False

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
