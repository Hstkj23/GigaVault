"""
Alert dispatcher — routes alerts to registered handlers.

Manages alert deduplication, rate limiting, and fan-out to
multiple notification channels concurrently.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any, Optional

from spawn_agent.alerts.base import Alert, AlertHandler

logger = logging.getLogger(__name__)


class AlertDispatcher:
    """
    Routes alerts to registered notification handlers.

    Features:
        - Fan-out to multiple handlers concurrently
        - Alert deduplication within a configurable window
        - Rate limiting per severity level
        - Buffered dispatch with configurable flush interval

    Args:
        dedup_window: Seconds to suppress duplicate alerts.
        rate_limit_info: Max info alerts per minute.
        rate_limit_warning: Max warning alerts per minute.
        rate_limit_critical: Max critical alerts per minute (0 = unlimited).
    """

    def __init__(
        self,
        dedup_window: float = 300.0,
        rate_limit_info: int = 30,
        rate_limit_warning: int = 60,
        rate_limit_critical: int = 0,
    ) -> None:
        self.dedup_window = dedup_window
        self._rate_limits = {
            "info": rate_limit_info,
            "warning": rate_limit_warning,
            "critical": rate_limit_critical,
        }
        self._handlers: list[AlertHandler] = []
        self._seen_hashes: dict[str, float] = {}
        self._rate_counters: dict[str, list[float]] = {
            "info": [],
            "warning": [],
            "critical": [],
        }
        self._queue: asyncio.Queue[Alert] = asyncio.Queue(maxsize=10000)
        self._running = False
        self._total_dispatched = 0
        self._total_suppressed = 0

    def register(self, handler: AlertHandler) -> None:
        """Register a notification handler."""
        self._handlers.append(handler)
        logger.info("Registered alert handler: %s", handler.name)

    def unregister(self, handler_name: str) -> bool:
        """Remove a handler by name."""
        before = len(self._handlers)
        self._handlers = [h for h in self._handlers if h.name != handler_name]
        return len(self._handlers) < before

    async def dispatch(self, alert: Alert) -> bool:
        """
        Dispatch an alert to all registered handlers.

        Returns False if the alert was suppressed by dedup or rate limiting.
        """
        # Deduplication
        alert_hash = self._hash_alert(alert)
        now = time.time()

        if alert_hash in self._seen_hashes:
            if now - self._seen_hashes[alert_hash] < self.dedup_window:
                self._total_suppressed += 1
                logger.debug("Suppressed duplicate alert: %s", alert.title)
                return False

        self._seen_hashes[alert_hash] = now

        # Rate limiting
        if not self._check_rate_limit(alert.severity):
            self._total_suppressed += 1
            logger.debug("Rate limited alert: %s", alert.title)
            return False

        # Fan out to all handlers
        tasks = [handler.safe_send(alert) for handler in self._handlers]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self._total_dispatched += 1
            return any(r is True for r in results)

        return False

    async def enqueue(self, alert: Alert) -> None:
        """Add an alert to the dispatch queue."""
        try:
            self._queue.put_nowait(alert)
        except asyncio.QueueFull:
            logger.warning("Alert queue full, dropping: %s", alert.title)

    async def run(self) -> None:
        """Process the alert queue continuously."""
        self._running = True
        while self._running:
            try:
                alert = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self.dispatch(alert)
            except asyncio.TimeoutError:
                # Prune old dedup entries
                self._prune_seen()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Dispatch error: %s", exc)

    async def stop(self) -> None:
        """Stop the dispatcher."""
        self._running = False

    def _check_rate_limit(self, severity: str) -> bool:
        """Check if the rate limit for this severity has been exceeded."""
        limit = self._rate_limits.get(severity, 0)
        if limit == 0:
            return True  # No limit

        now = time.time()
        window = self._rate_counters.get(severity, [])
        window = [t for t in window if now - t < 60]

        if len(window) >= limit:
            return False

        window.append(now)
        self._rate_counters[severity] = window
        return True

    def _prune_seen(self) -> None:
        """Remove old entries from the dedup cache."""
        now = time.time()
        self._seen_hashes = {
            h: t
            for h, t in self._seen_hashes.items()
            if now - t < self.dedup_window
        }

    @staticmethod
    def _hash_alert(alert: Alert) -> str:
        """Create a hash for alert deduplication."""
        key = f"{alert.title}:{alert.address}:{alert.severity}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "handlers": len(self._handlers),
            "dispatched": self._total_dispatched,
            "suppressed": self._total_suppressed,
            "queue_size": self._queue.qsize(),
        }
