"""
Data processing pipeline with concurrent stages.

Pipelines allow composing multiple analysis steps that run concurrently.
Events flow through stages with backpressure support via bounded queues.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

StageFunc = Callable[[dict[str, Any]], Coroutine[Any, Any, Optional[dict[str, Any]]]]


@dataclass
class PipelineStage:
    """A single stage in a processing pipeline."""

    name: str
    func: StageFunc
    concurrency: int = 1
    queue_size: int = 1000


class Pipeline:
    """
    Multi-stage concurrent event processing pipeline.

    Events enter the pipeline and flow through stages sequentially.
    Each stage can have its own concurrency level and queue depth,
    providing natural backpressure.

    Example::

        pipeline = Pipeline("tx_analysis")
        pipeline.add_stage("decode", decode_transaction, concurrency=4)
        pipeline.add_stage("enrich", enrich_with_labels, concurrency=2)
        pipeline.add_stage("detect", detect_anomalies, concurrency=2)
        pipeline.add_stage("alert", dispatch_alert, concurrency=1)

        await pipeline.start()
        await pipeline.push(event)
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._stages: list[PipelineStage] = []
        self._queues: list[asyncio.Queue] = []
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._processed_count = 0
        self._error_count = 0

    def add_stage(
        self,
        name: str,
        func: StageFunc,
        concurrency: int = 1,
        queue_size: int = 1000,
    ) -> Pipeline:
        """Add a processing stage to the pipeline."""
        self._stages.append(
            PipelineStage(
                name=name,
                func=func,
                concurrency=concurrency,
                queue_size=queue_size,
            )
        )
        return self

    async def start(self) -> None:
        """Start all pipeline stage workers."""
        self._running = True
        self._queues = [
            asyncio.Queue(maxsize=stage.queue_size) for stage in self._stages
        ]

        for idx, stage in enumerate(self._stages):
            for worker_id in range(stage.concurrency):
                task = asyncio.create_task(
                    self._stage_worker(idx, stage, worker_id)
                )
                self._tasks.append(task)

        logger.info(
            "Pipeline '%s' started with %d stages",
            self.name,
            len(self._stages),
        )

    async def stop(self) -> None:
        """Stop the pipeline gracefully."""
        self._running = False

        # Drain queues
        for queue in self._queues:
            while not queue.empty():
                try:
                    queue.get_nowait()
                    queue.task_done()
                except asyncio.QueueEmpty:
                    break

        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Pipeline '%s' stopped", self.name)

    async def push(self, event: dict[str, Any]) -> None:
        """Push an event into the pipeline's first stage."""
        if not self._queues:
            raise RuntimeError("Pipeline has not been started")
        await self._queues[0].put(event)

    async def _stage_worker(
        self, stage_idx: int, stage: PipelineStage, worker_id: int
    ) -> None:
        """Worker loop for a pipeline stage."""
        input_queue = self._queues[stage_idx]
        output_queue = (
            self._queues[stage_idx + 1]
            if stage_idx + 1 < len(self._queues)
            else None
        )

        while self._running:
            try:
                event = await asyncio.wait_for(input_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                result = await stage.func(event)
                if result is not None and output_queue is not None:
                    await output_queue.put(result)
                self._processed_count += 1
            except Exception as exc:
                self._error_count += 1
                logger.error(
                    "Pipeline '%s' stage '%s' worker %d error: %s",
                    self.name,
                    stage.name,
                    worker_id,
                    exc,
                )
            finally:
                input_queue.task_done()

    @property
    def stats(self) -> dict[str, Any]:
        """Pipeline processing statistics."""
        return {
            "name": self.name,
            "stages": len(self._stages),
            "processed": self._processed_count,
            "errors": self._error_count,
            "queue_depths": [q.qsize() for q in self._queues],
        }
