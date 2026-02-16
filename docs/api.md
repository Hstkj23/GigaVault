# API Reference

## spawn_agent.SpawnAgent

The main orchestrator class.

### Class Methods

#### `SpawnAgent.create(rpc_url, chain_id=1, **kwargs)`

Create a new agent instance with minimal configuration.

**Parameters:**
- `rpc_url` (str): JSON-RPC endpoint URL
- `chain_id` (int): Chain ID (default: 1 for Ethereum mainnet)
- `max_workers` (int): Maximum concurrent monitors (default: 1000)
- `log_level` (str): Logging level (default: "INFO")

**Returns:** `SpawnAgent`

#### `SpawnAgent.from_config(path)`

Create an agent from a YAML configuration file.

**Parameters:**
- `path` (str): Path to the YAML config file

**Returns:** `SpawnAgent`

---

### Instance Methods

#### `agent.watch(address, label=None, monitor_type="wallet")`

Register an address for monitoring.

**Parameters:**
- `address` (str): Hex address to monitor (0x-prefixed)
- `label` (str, optional): Human-readable label
- `monitor_type` (str): Monitor type — `"wallet"`, `"contract"`, `"mempool"`, or `"dex"`

**Returns:** `str` — The normalized address (monitor ID)

**Raises:** `RuntimeError` if max_workers limit is reached

#### `agent.unwatch(address)`

Stop monitoring an address.

**Parameters:**
- `address` (str): Address to stop monitoring

**Returns:** `bool` — True if the address was being monitored

#### `agent.on(event_type)`

Decorator to register an event handler.

```python
@agent.on("large_transfer")
async def handler(event):
    print(event)
```

**Parameters:**
- `event_type` (str): Event type name, or `"*"` for all events

#### `agent.add_handler(event_type, handler)`

Register an event handler function directly.

**Parameters:**
- `event_type` (str): Event type name
- `handler` (Callable): Async function accepting an event dict

#### `await agent.start()`

Start the agent and all registered monitors. Blocks until stopped.

#### `await agent.stop()`

Gracefully stop the agent and all monitors.

---

## spawn_agent.Supervisor

OTP-inspired supervision tree.

### Constructor

```python
Supervisor(
    restart_strategy=RestartStrategy.ONE_FOR_ONE,
    max_restarts=5,
    restart_window=60.0,
)
```

### Methods

- `supervisor.register(worker)` — Add a worker process
- `supervisor.unregister(process_id)` — Remove a worker process
- `await supervisor.start_all()` — Start all registered workers
- `await supervisor.stop_all()` — Stop all workers gracefully
- `supervisor.get_status()` — Get health status of all workers

---

## spawn_agent.WorkerProcess

Wraps a monitor target as a supervised process.

### Constructor

```python
WorkerProcess(process_id, target, on_event=None)
```

### Properties

- `state` — Current `ProcessState` (IDLE, STARTING, RUNNING, etc.)
- `uptime` — Seconds since last start
- `event_count` — Total events processed

---

## Analysis Modules

### WalletGraph

```python
from spawn_agent.analysis.graph import WalletGraph

graph = WalletGraph()
graph.add_transaction(tx_dict)
result = graph.trace_forward("0x...", max_depth=3)
path = graph.shortest_path("0xA", "0xB")
clusters = graph.find_clusters(min_connections=2)
```

### AnomalyDetector

```python
from spawn_agent.analysis.anomaly import AnomalyDetector

detector = AnomalyDetector(volume_threshold=5.0)
anomalies = detector.analyze(event)
circular = detector.detect_circular_flows(window_seconds=300)
```

### PatternMatcher

```python
from spawn_agent.analysis.patterns import PatternMatcher

matcher = PatternMatcher(min_confidence=0.6)
matches = matcher.ingest(transaction)
all_matches = matcher.scan_buffer()
```

### WalletClusterer

```python
from spawn_agent.analysis.cluster import WalletClusterer

clusterer = WalletClusterer()
clusterer.add_transaction(tx_dict)
clusters = clusterer.get_clusters(min_size=3)
```

---

## Alert System

### Alert

```python
from spawn_agent.alerts.base import Alert

alert = Alert(
    title="Large Transfer",
    message="10 ETH moved from 0x... to 0x...",
    severity="warning",  # info, warning, critical
    address="0x...",
    tx_hash="0x...",
)
```

### AlertDispatcher

```python
from spawn_agent.alerts.dispatcher import AlertDispatcher
from spawn_agent.alerts.telegram import TelegramAlertHandler

dispatcher = AlertDispatcher(dedup_window=300.0)
dispatcher.register(TelegramAlertHandler(bot_token="...", chat_id="..."))
await dispatcher.dispatch(alert)
```

---

## Configuration

### AgentConfig

```python
from spawn_agent.utils.config import AgentConfig

# From YAML file
config = AgentConfig.from_yaml("config/spawn_agent.yml")

# From dict
config = AgentConfig.from_dict({
    "provider": {"rpc_url": "https://..."},
    "monitoring": {"poll_interval": 2.0},
})

# Environment variable overrides (SPAWN_AGENT_* prefix)
# SPAWN_AGENT_RPC_URL overrides config.rpc_url
# SPAWN_AGENT_CHAIN_ID overrides config.chain_id
```

---

## Event Types

| Event Type          | Source     | Description                          |
|---------------------|-----------|--------------------------------------|
| `transfer_in`       | Wallet    | Incoming ETH transfer                |
| `transfer_out`      | Wallet    | Outgoing ETH transfer                |
| `token_transfer`    | Wallet    | ERC-20 token transfer                |
| `balance_change`    | Wallet    | Significant balance change           |
| `large_transfer`    | Wallet    | Transfer exceeding threshold         |
| `new_interaction`   | Wallet    | First interaction with an address    |
| `function_call`     | Contract  | Function invocation on contract      |
| `contract_event`    | Contract  | Log event emitted by contract        |
| `new_caller`        | Contract  | First-time caller to contract        |
| `high_frequency`    | Contract  | Unusual call frequency               |
| `pending_tx`        | Mempool   | New pending transaction              |
| `large_pending`     | Mempool   | Large pending transfer               |
| `swap`              | DEX       | Token swap event                     |
| `mint`              | DEX       | Liquidity addition                   |
| `burn`              | DEX       | Liquidity removal                    |
