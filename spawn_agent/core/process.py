"""
Worker process abstraction for supervised async tasks.

Each WorkerProcess wraps a monitor or analysis task and provides
lifecycle management, state tracking, and event routing.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from typing import Any, Callable, Coroutine, Optional, Protocol

logger = logging.getLogger(__name__)


class ProcessState(enum.Enum):
    """Lifecycle states for a worker process."""

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    RESTARTING = "restarting"
    STOPPED = "stopped"
    TERMINATED = "terminated"


class MonitorProtocol(Protocol):
    """Protocol that all monitors must implement."""

    address: str
    label: Optional[str]

    async def start(self, event_callback: Callable) -> None: ...
    async def stop(self) -> None: ...


class WorkerProcess:
    """
    A supervised async worker wrapping a monitor target.

    The worker manages the lifecycle of its target monitor, tracks
    state transitions, and routes events to the agent's dispatcher.

    Args:
        process_id: Unique identifier for this worker (typically the address).
        target: The monitor instance to run.
        on_event: Callback for dispatching events to the agent.
    """

    def __init__(
        self,
        process_id: str,
        target: MonitorProtocol,
        on_event: Optional[Callable[..., Coroutine[Any, Any, None]]] = None,
    ) -> None:
        self.process_id = process_id
        self.target = target
        self.on_event = on_event
        self.state = ProcessState.IDLE
        self._started_at: Optional[float] = None
        self._stopped_at: Optional[float] = None
        self._event_count: int = 0

    async def run(self) -> None:
        """Execute the target monitor's main loop."""
        self.state = ProcessState.STARTING
        self._started_at = time.monotonic()
        self._event_count = 0

        logger.debug("Worker %s starting", self.process_id)

        try:
            self.state = ProcessState.RUNNING
            await self.target.start(event_callback=self._handle_event)
        finally:
            self._stopped_at = time.monotonic()

    async def stop(self) -> None:
        """Stop the target monitor."""
        self.state = ProcessState.STOPPED
        try:
            await self.target.stop()
        except Exception:
            logger.exception("Error stopping worker %s", self.process_id)
        self._stopped_at = time.monotonic()

    async def _handle_event(self, event: dict[str, Any]) -> None:
        """Route events from the monitor to the agent dispatcher."""
        self._event_count += 1
        event.setdefault("source", self.process_id)
        event.setdefault("timestamp", time.time())

        if self.on_event:
            await self.on_event(event)

    @property
    def uptime(self) -> float:
        """Uptime in seconds since the worker started."""
        if self._started_at is None:
            return 0.0
        end = self._stopped_at or time.monotonic()
        return end - self._started_at

    @property
    def event_count(self) -> int:
        """Total events processed by this worker."""
        return self._event_count

    def __repr__(self) -> str:
        return (
            f"<WorkerProcess id={self.process_id} state={self.state.value} "
            f"events={self._event_count}>"
        )
