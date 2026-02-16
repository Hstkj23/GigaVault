"""Alert dispatching and notification handlers."""

from spawn_agent.alerts.dispatcher import AlertDispatcher
from spawn_agent.alerts.base import AlertHandler
from spawn_agent.alerts.telegram import TelegramAlertHandler
from spawn_agent.alerts.discord import DiscordAlertHandler
from spawn_agent.alerts.webhook import WebhookAlertHandler

__all__ = [
    "AlertDispatcher",
    "AlertHandler",
    "TelegramAlertHandler",
    "DiscordAlertHandler",
    "WebhookAlertHandler",
]
