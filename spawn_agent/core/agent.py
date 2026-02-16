"""
Main SpawnAgent orchestrator.

The SpawnAgent class is the primary entry point for configuring and running
the monitoring platform. It manages the lifecycle of monitors, analysis
pipelines, and alert dispatchers.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

import yaml

from spawn_agent.core.supervisor import Supervisor, RestartStrategy
from spawn_agent.core.process import WorkerProcess
from spawn_agent.monitors.wallet import WalletMonitor
from spawn_agent.monitors.contract import ContractMonitor
from spawn_agent.providers.rpc import RPCProvider
from spawn_agent.providers.websocket import WebSocketProvider
from spawn_agent.alerts.dispatcher import AlertDispatcher
from spawn_agent.utils.config import AgentConfig
from spawn_agent.utils.logging import setup_logging

logger = logging.getLogger(__name__)

EventCallback = Callable[..., Coroutine[Any, Any, None]]


class SpawnAgent:
    """
    Main orchestrator for on-chain monitoring and analysis.

    The agent manages a supervision tree of monitor workers, each responsible
    for a single address or contract. Events flow through analysis pipelines
    and are dispatched to registered alert handlers.

    Example::

        agent = SpawnAgent.from_config("config/spawn_agent.yml")
        agent.watch("0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68")

        @agent.on("large_transfer")
        async def on_large(event):
            print(event)

        await agent.start()
    """

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._supervisor = Supervisor(
            max_restarts=config.supervisor_restart_limit,
            restart_strategy=RestartStrategy.ONE_FOR_ONE,
        )
        self._rpc_provider: Optional[RPCProvider] = None
        self._ws_provider: Optional[WebSocketProvider] = None
        self._alert_dispatcher = AlertDispatcher()
        self._event_handlers: dict[str, list[EventCallback]] = {}
        self._monitors: dict[str, WorkerProcess] = {}
        self._running = False
        self._tasks: list[asyncio.Task] = []

        setup_logging(config.log_level)

    @classmethod
    def from_config(cls, path: str | Path) -> SpawnAgent:
        """Create an agent from a YAML configuration file."""
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, "r") as f:
            raw = yaml.safe_load(f)

        config = AgentConfig.from_dict(raw)
        return cls(config)

    @classmethod
    def create(
        cls,
        rpc_url: str,
        chain_id: int = 1,
        max_workers: int = 1000,
        log_level: str = "INFO",
    ) -> SpawnAgent:
        """Create an agent with minimal programmatic configuration."""
        config = AgentConfig(
            rpc_url=rpc_url,
            chain_id=chain_id,
            max_workers=max_workers,
            log_level=log_level,
        )
        return cls(config)

    def watch(
        self,
        address: str,
        *,
        label: Optional[str] = None,
        monitor_type: str = "wallet",
        options: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Start monitoring an address.

        Args:
            address: The blockchain address to monitor.
            label: Optional human-readable label for the address.
            monitor_type: Type of monitor ("wallet" or "contract").
            options: Additional monitor-specific options.

        Returns:
            The monitor ID for this address.
        """
        address = address.lower().strip()
        if address in self._monitors:
            logger.warning("Address %s is already being monitored", address)
            return address

        if len(self._monitors) >= self.config.max_workers:
            raise RuntimeError(
                f"Maximum worker count ({self.config.max_workers}) reached. "
                "Increase max_workers in configuration to monitor more addresses."
            )

        if monitor_type == "contract":
            monitor = ContractMonitor(
                address=address,
                label=label,
                provider=self._rpc_provider,
                options=options or {},
            )
        else:
            monitor = WalletMonitor(
                address=address,
                label=label,
                provider=self._rpc_provider,
                options=options or {},
            )

        worker = WorkerProcess(
            process_id=address,
            target=monitor,
            on_event=self._dispatch_event,
        )
        self._supervisor.register(worker)
        self._monitors[address] = worker
        logger.info("Spawned monitor for %s [%s]", label or address, monitor_type)
        return address

    def unwatch(self, address: str) -> bool:
        """Stop monitoring an address."""
        address = address.lower().strip()
        worker = self._monitors.pop(address, None)
        if worker is None:
            return False

        self._supervisor.unregister(worker.process_id)
        logger.info("Stopped monitoring %s", address)
        return True

    def on(self, event_type: str) -> Callable[[EventCallback], EventCallback]:
        """Register an event handler via decorator."""

        def decorator(func: EventCallback) -> EventCallback:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = []
            self._event_handlers[event_type].append(func)
            return func

        return decorator

    def add_handler(self, event_type: str, handler: EventCallback) -> None:
        """Register an event handler programmatically."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    async def _dispatch_event(self, event: dict[str, Any]) -> None:
        """Route an event to registered handlers and the alert dispatcher."""
        event_type = event.get("type", "unknown")
        handlers = self._event_handlers.get(event_type, [])
        wildcard_handlers = self._event_handlers.get("*", [])

        all_handlers = handlers + wildcard_handlers
        if not all_handlers:
            return

        tasks = [
            asyncio.create_task(self._safe_call(handler, event))
            for handler in all_handlers
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _safe_call(handler: EventCallback, event: dict[str, Any]) -> None:
        """Call a handler with exception isolation."""
        try:
            await handler(event)
        except Exception:
            logger.exception("Error in event handler %s", handler.__name__)

    async def _initialize_providers(self) -> None:
        """Set up RPC and WebSocket providers."""
        self._rpc_provider = RPCProvider(
            url=self.config.rpc_url,
            chain_id=self.config.chain_id,
            max_connections=self.config.max_connections,
            timeout=self.config.rpc_timeout,
        )
        await self._rpc_provider.connect()

        if self.config.ws_url:
            self._ws_provider = WebSocketProvider(
                url=self.config.ws_url,
                reconnect_interval=self.config.ws_reconnect_interval,
            )
            await self._ws_provider.connect()

    async def start(self) -> None:
        """
        Start the agent and all registered monitors.

        This method blocks until the agent is stopped via signal or
        the ``stop()`` method.
        """
        logger.info(
            "Starting SpawnAgent v%s with %d monitors",
            __import__("spawn_agent").__version__,
            len(self._monitors),
        )
        self._running = True

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        await self._initialize_providers()

        # Inject the live provider into all monitors
        for worker in self._monitors.values():
            worker.target.provider = self._rpc_provider

        # Start the supervision tree
        supervisor_task = asyncio.create_task(self._supervisor.start())
        self._tasks.append(supervisor_task)

        # Start alert dispatcher
        dispatcher_task = asyncio.create_task(
            self._alert_dispatcher.run()
        )
        self._tasks.append(dispatcher_task)

        logger.info("SpawnAgent is running. Press Ctrl+C to stop.")

        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            logger.info("Agent tasks cancelled")

    async def stop(self) -> None:
        """Gracefully shut down the agent."""
        if not self._running:
            return

        logger.info("Shutting down SpawnAgent...")
        self._running = False

        await self._supervisor.stop()
        await self._alert_dispatcher.stop()

        for task in self._tasks:
            task.cancel()

        if self._rpc_provider:
            await self._rpc_provider.close()
        if self._ws_provider:
            await self._ws_provider.close()

        logger.info("SpawnAgent stopped.")

    @property
    def monitor_count(self) -> int:
        """Number of active monitors."""
        return len(self._monitors)

    @property
    def is_running(self) -> bool:
        """Whether the agent is currently running."""
        return self._running

    def __repr__(self) -> str:
        status = "running" if self._running else "stopped"
        return (
            f"<SpawnAgent status={status} monitors={len(self._monitors)} "
            f"chain_id={self.config.chain_id}>"
        )
