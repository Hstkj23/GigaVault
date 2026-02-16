"""Tests for the alert dispatcher and handlers."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from spawn_agent.alerts.base import Alert, AlertHandler
from spawn_agent.alerts.dispatcher import AlertDispatcher


class MockHandler(AlertHandler):
    """Test alert handler that records sent alerts."""

    def __init__(self):
        super().__init__(name="mock")
        self.sent_alerts = []

    async def send(self, alert: Alert) -> bool:
        self.sent_alerts.append(alert)
        return True


class FailingHandler(AlertHandler):
    """Test handler that always fails."""

    def __init__(self):
        super().__init__(name="failing")

    async def send(self, alert: Alert) -> bool:
        raise RuntimeError("Send failed")


class TestAlert:
    """Test alert data structure."""

    def test_create_alert(self):
        alert = Alert(
            title="Large Transfer",
            message="10 ETH moved",
            severity="warning",
            address="0xabc",
        )
        assert alert.title == "Large Transfer"
        assert alert.severity == "warning"

    def test_to_dict(self):
        alert = Alert(title="Test", message="msg", severity="info")
        d = alert.to_dict()
        assert d["title"] == "Test"
        assert d["severity"] == "info"

    def test_format_text(self):
        alert = Alert(
            title="Alert",
            message="Something happened",
            severity="critical",
            address="0x123",
            tx_hash="0xabc",
        )
        text = alert.format_text()
        assert "[CRITICAL]" in text
        assert "0x123" in text

    def test_format_markdown(self):
        alert = Alert(
            title="Alert",
            message="Something happened",
            severity="warning",
        )
        md = alert.format_markdown()
        assert "**Alert**" in md
        assert "⚠️" in md


class TestAlertDispatcher:
    """Test alert dispatch and deduplication."""

    @pytest.mark.asyncio
    async def test_dispatch_to_handler(self):
        dispatcher = AlertDispatcher()
        handler = MockHandler()
        dispatcher.register(handler)

        alert = Alert(title="Test", message="test", severity="info")
        result = await dispatcher.dispatch(alert)
        assert result is True
        assert len(handler.sent_alerts) == 1

    @pytest.mark.asyncio
    async def test_dispatch_deduplication(self):
        dispatcher = AlertDispatcher(dedup_window=60.0)
        handler = MockHandler()
        dispatcher.register(handler)

        alert = Alert(title="Dup", message="same", severity="info", address="0x1")

        await dispatcher.dispatch(alert)
        await dispatcher.dispatch(alert)  # Should be deduplicated

        assert len(handler.sent_alerts) == 1

    @pytest.mark.asyncio
    async def test_dispatch_different_alerts_not_deduped(self):
        dispatcher = AlertDispatcher()
        handler = MockHandler()
        dispatcher.register(handler)

        await dispatcher.dispatch(Alert(title="A", message="1", severity="info"))
        await dispatcher.dispatch(Alert(title="B", message="2", severity="info"))

        assert len(handler.sent_alerts) == 2

    @pytest.mark.asyncio
    async def test_failing_handler_doesnt_crash(self):
        dispatcher = AlertDispatcher()
        dispatcher.register(FailingHandler())

        alert = Alert(title="Test", message="test", severity="info")
        result = await dispatcher.dispatch(alert)
        # Should not raise, handler failure is isolated
        assert result is False

    @pytest.mark.asyncio
    async def test_multiple_handlers(self):
        dispatcher = AlertDispatcher()
        h1 = MockHandler()
        h2 = MockHandler()
        dispatcher.register(h1)
        dispatcher.register(h2)

        alert = Alert(title="Multi", message="test", severity="info")
        await dispatcher.dispatch(alert)

        assert len(h1.sent_alerts) == 1
        assert len(h2.sent_alerts) == 1

    def test_register_unregister(self):
        dispatcher = AlertDispatcher()
        handler = MockHandler()
        dispatcher.register(handler)
        assert len(dispatcher._handlers) == 1

        dispatcher.unregister("mock")
        assert len(dispatcher._handlers) == 0

    def test_stats(self):
        dispatcher = AlertDispatcher()
        stats = dispatcher.stats
        assert stats["handlers"] == 0
        assert stats["dispatched"] == 0
        assert stats["suppressed"] == 0
