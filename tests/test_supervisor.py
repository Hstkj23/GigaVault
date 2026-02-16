"""Tests for the supervisor and process modules."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from spawn_agent.core.process import WorkerProcess, ProcessState
from spawn_agent.core.supervisor import Supervisor, RestartStrategy


class TestWorkerProcess:
    """Test worker process lifecycle."""

    def test_initial_state(self):
        target = MagicMock()
        target.address = "0x123"
        target.label = "test"
        worker = WorkerProcess(process_id="test-1", target=target)
        assert worker.state == ProcessState.IDLE
        assert worker.event_count == 0
        assert worker.uptime == 0.0

    def test_repr(self):
        target = MagicMock()
        worker = WorkerProcess(process_id="0xabc", target=target)
        r = repr(worker)
        assert "0xabc" in r
        assert "idle" in r

    @pytest.mark.asyncio
    async def test_event_routing(self):
        target = AsyncMock()
        events_received = []

        async def on_event(event):
            events_received.append(event)

        worker = WorkerProcess(
            process_id="test-1", target=target, on_event=on_event
        )
        await worker._handle_event({"type": "test", "data": 42})

        assert len(events_received) == 1
        assert events_received[0]["source"] == "test-1"
        assert worker.event_count == 1


class TestSupervisor:
    """Test supervision tree behavior."""

    def test_init_defaults(self):
        supervisor = Supervisor()
        assert supervisor.max_restarts == 5
        assert supervisor.restart_strategy == RestartStrategy.ONE_FOR_ONE
        assert supervisor.worker_count == 0

    def test_register_worker(self):
        supervisor = Supervisor()
        target = MagicMock()
        worker = WorkerProcess(process_id="w1", target=target)
        supervisor.register(worker)
        assert supervisor.worker_count == 1

    def test_unregister_worker(self):
        supervisor = Supervisor()
        target = MagicMock()
        worker = WorkerProcess(process_id="w1", target=target)
        supervisor.register(worker)
        supervisor.unregister("w1")
        assert supervisor.worker_count == 0

    def test_unregister_nonexistent(self):
        supervisor = Supervisor()
        supervisor.unregister("nonexistent")  # Should not raise
        assert supervisor.worker_count == 0

    def test_get_status(self):
        supervisor = Supervisor()
        target = MagicMock()
        worker = WorkerProcess(process_id="w1", target=target)
        supervisor.register(worker)
        status = supervisor.get_status()
        assert status["total"] == 1
        assert "w1" in status["workers"]

    def test_restart_strategies(self):
        for strategy in RestartStrategy:
            supervisor = Supervisor(restart_strategy=strategy)
            assert supervisor.restart_strategy == strategy
