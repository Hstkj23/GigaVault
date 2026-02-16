"""
Base monitor interface.

All monitors implement this base class, which provides the common
lifecycle methods and configuration interface.
"""

from __future__ import annotations

import abc
import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

EventCallback = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class BaseMonitor(abc.ABC):
    """
    Abstract base class for all monitors.

    Subclasses must implement ``_poll_loop`` or ``_subscribe`` to define
    how on-chain data is collected. The monitor handles lifecycle,
    reconnection, and event dispatching.

    Args:
        address: The blockchain address to monitor.
        label: Optional human-readable label.
        provider: RPC/WebSocket provider instance.
        options: Monitor-specific configuration options.
    """

    def __init__(
        self,
        address: str,
        label: Optional[str] = None,
        provider: Any = None,
        options: Optional[dict[str, Any]] = None,
    ) -> None:
        self.address = address.lower()
        self.label = label or address[:10]
        self.provider = provider
        self.options = options or {}
        self._event_callback: Optional[EventCallback] = None
        self._running = False
        self._poll_interval = self.options.get("poll_interval", 2.0)
        self._last_block: Optional[int] = None

    async def start(self, event_callback: EventCallback) -> None:
        """Start the monitor's main loop."""
        self._event_callback = event_callback
        self._running = True

        logger.debug("Monitor starting for %s", self.address)

        try:
            await self._run()
        finally:
            self._running = False

    async def stop(self) -> None:
        """Signal the monitor to stop."""
        self._running = False

    @abc.abstractmethod
    async def _run(self) -> None:
        """Main monitoring loop. Must be implemented by subclasses."""
        ...

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit an event to the event callback."""
        if self._event_callback is None:
            return

        event = {
            "type": event_type,
            "address": self.address,
            "label": self.label,
            **data,
        }
        await self._event_callback(event)

    async def _get_current_block(self) -> int:
        """Fetch the current block number from the provider."""
        if self.provider is None:
            raise RuntimeError("No provider configured")
        return await self.provider.get_block_number()

    def __repr__(self) -> str:
        status = "running" if self._running else "stopped"
        return f"<{self.__class__.__name__} address={self.address[:10]}... status={status}>"
