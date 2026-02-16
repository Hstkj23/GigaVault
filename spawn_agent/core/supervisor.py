"""
Supervision tree for managing worker processes.

Inspired by OTP supervisor patterns, this module provides automatic
restart strategies, circuit breaking, and health monitoring for
long-running async workers.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from spawn_agent.core.process import WorkerProcess, ProcessState

logger = logging.getLogger(__name__)


class RestartStrategy(enum.Enum):
    """Strategy for restarting failed workers."""

    ONE_FOR_ONE = "one_for_one"
    ONE_FOR_ALL = "one_for_all"
    REST_FOR_ONE = "rest_for_one"


@dataclass
class RestartRecord:
    """Tracks restart attempts for circuit breaking."""

    timestamps: list[float] = field(default_factory=list)

    def record(self) -> None:
        self.timestamps.append(time.monotonic())

    def count_within(self, window_seconds: float) -> int:
        cutoff = time.monotonic() - window_seconds
        self.timestamps = [t for t in self.timestamps if t > cutoff]
        return len(self.timestamps)


class Supervisor:
    """
    Manages a tree of worker processes with automatic restart capabilities.

    The supervisor monitors registered workers and restarts them according
    to the configured strategy when they fail. A circuit breaker prevents
    restart storms by limiting the number of restarts within a time window.

    Args:
        max_restarts: Maximum restarts allowed within the restart window.
        restart_window: Time window in seconds for counting restarts.
        restart_strategy: Strategy for handling worker failures.
        backoff_base: Base delay in seconds for exponential backoff.
        backoff_max: Maximum backoff delay in seconds.
    """

    def __init__(
        self,
        max_restarts: int = 5,
        restart_window: float = 60.0,
        restart_strategy: RestartStrategy = RestartStrategy.ONE_FOR_ONE,
        backoff_base: float = 1.0,
        backoff_max: float = 30.0,
    ) -> None:
        self.max_restarts = max_restarts
        self.restart_window = restart_window
        self.restart_strategy = restart_strategy
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self._workers: dict[str, WorkerProcess] = {}
        self._restart_records: dict[str, RestartRecord] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False
        self._health_task: Optional[asyncio.Task] = None

    def register(self, worker: WorkerProcess) -> None:
        """Register a worker process under this supervisor."""
        self._workers[worker.process_id] = worker
        self._restart_records[worker.process_id] = RestartRecord()
        logger.debug("Registered worker: %s", worker.process_id)

    def unregister(self, process_id: str) -> None:
        """Remove a worker from supervision."""
        worker = self._workers.pop(process_id, None)
        self._restart_records.pop(process_id, None)
        task = self._tasks.pop(process_id, None)

        if task and not task.done():
            task.cancel()

        if worker:
            logger.debug("Unregistered worker: %s", process_id)

    async def start(self) -> None:
        """Start supervising all registered workers."""
        self._running = True
        logger.info(
            "Supervisor starting with %d workers [strategy=%s]",
            len(self._workers),
            self.restart_strategy.value,
        )

        # Launch all workers
        for process_id, worker in self._workers.items():
            self._tasks[process_id] = asyncio.create_task(
                self._run_worker(process_id)
            )

        # Start health monitoring
        self._health_task = asyncio.create_task(self._health_check_loop())

        # Wait for all tasks
        try:
            await asyncio.gather(
                *self._tasks.values(),
                self._health_task,
                return_exceptions=True,
            )
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        """Stop all supervised workers."""
        self._running = False

        if self._health_task and not self._health_task.done():
            self._health_task.cancel()

        for process_id, task in list(self._tasks.items()):
            if not task.done():
                task.cancel()

        # Allow workers to clean up
        for worker in self._workers.values():
            try:
                await asyncio.wait_for(worker.stop(), timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                logger.warning("Worker %s did not stop cleanly", worker.process_id)

        logger.info("Supervisor stopped")

    async def _run_worker(self, process_id: str) -> None:
        """Run a worker with automatic restart on failure."""
        consecutive_failures = 0

        while self._running and process_id in self._workers:
            worker = self._workers[process_id]
            record = self._restart_records.get(process_id)

            if record and record.count_within(self.restart_window) >= self.max_restarts:
                logger.error(
                    "Worker %s exceeded max restarts (%d in %ds). "
                    "Circuit breaker triggered.",
                    process_id,
                    self.max_restarts,
                    self.restart_window,
                )
                worker.state = ProcessState.TERMINATED
                break

            try:
                worker.state = ProcessState.RUNNING
                await worker.run()
                # Clean exit
                consecutive_failures = 0
                if not self._running:
                    break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                consecutive_failures += 1
                worker.state = ProcessState.RESTARTING

                if record:
                    record.record()

                backoff = min(
                    self.backoff_base * (2 ** (consecutive_failures - 1)),
                    self.backoff_max,
                )
                logger.warning(
                    "Worker %s failed: %s. Restarting in %.1fs (attempt %d)",
                    process_id,
                    str(exc),
                    backoff,
                    consecutive_failures,
                )

                if self.restart_strategy == RestartStrategy.ONE_FOR_ALL:
                    await self._restart_all_except(process_id)

                await asyncio.sleep(backoff)

    async def _restart_all_except(self, failed_id: str) -> None:
        """Restart all workers when one fails (ONE_FOR_ALL strategy)."""
        for pid, task in list(self._tasks.items()):
            if pid != failed_id and not task.done():
                task.cancel()
                worker = self._workers.get(pid)
                if worker:
                    worker.state = ProcessState.RESTARTING

        # Re-launch after a brief delay
        await asyncio.sleep(0.5)
        for pid in self._workers:
            if pid != failed_id and pid not in self._tasks:
                self._tasks[pid] = asyncio.create_task(self._run_worker(pid))

    async def _health_check_loop(self) -> None:
        """Periodically check worker health."""
        while self._running:
            await asyncio.sleep(30.0)
            healthy = sum(
                1
                for w in self._workers.values()
                if w.state == ProcessState.RUNNING
            )
            total = len(self._workers)
            logger.debug(
                "Health check: %d/%d workers healthy", healthy, total
            )

    @property
    def worker_count(self) -> int:
        return len(self._workers)

    @property
    def healthy_count(self) -> int:
        return sum(
            1
            for w in self._workers.values()
            if w.state == ProcessState.RUNNING
        )

    def get_status(self) -> dict:
        """Get a status summary of all workers."""
        return {
            "total": self.worker_count,
            "healthy": self.healthy_count,
            "strategy": self.restart_strategy.value,
            "workers": {
                pid: {
                    "state": w.state.value,
                    "label": w.target.label if hasattr(w.target, "label") else None,
                }
                for pid, w in self._workers.items()
            },
        }
