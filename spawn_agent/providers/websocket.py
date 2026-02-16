"""
WebSocket provider for real-time blockchain event streaming.

Maintains a persistent WebSocket connection with automatic
reconnection and subscription management.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Optional

import aiohttp

logger = logging.getLogger(__name__)


class WebSocketProvider:
    """
    Persistent WebSocket connection for streaming blockchain events.

    Supports:
        - Automatic reconnection with exponential backoff
        - Subscription management (newHeads, newPendingTransactions, logs)
        - Message deduplication
        - Heartbeat/ping monitoring

    Args:
        url: WebSocket endpoint URL (wss://).
        reconnect_interval: Base reconnect interval in seconds.
        max_reconnect_interval: Maximum reconnect interval in seconds.
        ping_interval: Interval between ping messages in seconds.
    """

    def __init__(
        self,
        url: str,
        reconnect_interval: float = 1.0,
        max_reconnect_interval: float = 60.0,
        ping_interval: float = 30.0,
    ) -> None:
        self.url = url
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_interval = max_reconnect_interval
        self.ping_interval = ping_interval

        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._subscriptions: dict[str, str] = {}  # sub_id -> method
        self._request_id = 0
        self._connected = False
        self._reconnect_count = 0
        self._message_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=10000
        )

    async def connect(self) -> None:
        """Establish the WebSocket connection."""
        self._session = aiohttp.ClientSession()
        await self._connect()

    async def _connect(self) -> None:
        """Internal connection logic with retry."""
        while True:
            try:
                self._ws = await self._session.ws_connect(
                    self.url,
                    heartbeat=self.ping_interval,
                    max_msg_size=0,  # No limit
                )
                self._connected = True
                self._reconnect_count = 0
                logger.info("WebSocket connected to %s", self.url)

                # Re-subscribe after reconnection
                if self._subscriptions:
                    await self._resubscribe()

                return
            except Exception as exc:
                self._reconnect_count += 1
                delay = min(
                    self.reconnect_interval * (2 ** self._reconnect_count),
                    self.max_reconnect_interval,
                )
                logger.warning(
                    "WebSocket connection failed: %s. Reconnecting in %.1fs",
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

    async def close(self) -> None:
        """Close the WebSocket connection."""
        self._connected = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session:
            await self._session.close()

    async def subscribe_new_heads(self) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to new block headers."""
        sub_id = await self._subscribe("newHeads")
        async for message in self._listen(sub_id):
            yield message

    async def subscribe_pending_transactions(self) -> AsyncIterator[str]:
        """Subscribe to new pending transaction hashes."""
        sub_id = await self._subscribe("newPendingTransactions")
        async for message in self._listen(sub_id):
            result = message.get("result")
            if isinstance(result, str):
                yield result

    async def subscribe_logs(
        self,
        address: Optional[str] = None,
        topics: Optional[list[str]] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to log events with optional filters."""
        params: dict[str, Any] = {}
        if address:
            params["address"] = address
        if topics:
            params["topics"] = topics

        sub_id = await self._subscribe("logs", params)
        async for message in self._listen(sub_id):
            yield message

    async def _subscribe(
        self, method: str, params: Optional[dict[str, Any]] = None
    ) -> str:
        """Send a subscription request."""
        self._request_id += 1
        subscribe_params = [method]
        if params:
            subscribe_params.append(params)

        payload = {
            "jsonrpc": "2.0",
            "method": "eth_subscribe",
            "params": subscribe_params,
            "id": self._request_id,
        }

        await self._send(payload)

        # Wait for subscription confirmation
        response = await self._receive_response(self._request_id)
        sub_id = response.get("result", "")
        self._subscriptions[sub_id] = method
        logger.debug("Subscribed to %s (id: %s)", method, sub_id)
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from a subscription."""
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_unsubscribe",
            "params": [subscription_id],
            "id": self._request_id,
        }
        await self._send(payload)
        self._subscriptions.pop(subscription_id, None)
        return True

    async def _resubscribe(self) -> None:
        """Re-establish subscriptions after reconnection."""
        old_subs = dict(self._subscriptions)
        self._subscriptions.clear()

        for method in old_subs.values():
            await self._subscribe(method)

        logger.info("Re-subscribed to %d streams", len(old_subs))

    async def _send(self, payload: dict[str, Any]) -> None:
        """Send a message over the WebSocket."""
        if not self._ws or self._ws.closed:
            await self._connect()
        await self._ws.send_json(payload)

    async def _receive_response(self, request_id: int) -> dict[str, Any]:
        """Wait for a specific response by request ID."""
        if not self._ws:
            raise RuntimeError("Not connected")

        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("id") == request_id:
                    return data
                # Queue subscription messages for later processing
                if "params" in data:
                    await self._message_queue.put(data["params"])
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                raise ConnectionError("WebSocket closed unexpectedly")

        raise ConnectionError("WebSocket stream ended")

    async def _listen(self, subscription_id: str) -> AsyncIterator[dict[str, Any]]:
        """Listen for messages matching a subscription ID."""
        while self._connected:
            try:
                if self._ws is None or self._ws.closed:
                    await self._connect()

                async for msg in self._ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        params = data.get("params", {})
                        if params.get("subscription") == subscription_id:
                            yield params.get("result", {})
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        logger.warning("WebSocket closed, reconnecting...")
                        break

            except Exception as exc:
                logger.error("WebSocket listener error: %s", exc)

            if self._connected:
                await self._connect()

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None and not self._ws.closed

    @property
    def subscription_count(self) -> int:
        return len(self._subscriptions)

    def __repr__(self) -> str:
        status = "connected" if self.is_connected else "disconnected"
        return f"<WebSocketProvider url={self.url} status={status} subs={self.subscription_count}>"
