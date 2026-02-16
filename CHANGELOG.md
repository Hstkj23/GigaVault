# Changelog

All notable changes to SpawnAgent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.2] - 2025-06-14

### Fixed
- WebSocket reconnect loop not resetting backoff after successful connection
- Wallet monitor missing ERC-20 transfer events with non-standard log formats
- Pipeline stage error counter not incrementing on filtered events

### Changed
- Improved anomaly detection EMA smoothing factor (0.1 → 0.15)
- Reduced default supervisor health check interval from 60s to 30s

## [0.4.1] - 2025-05-28

### Fixed
- Alert dispatcher dedup hash collision on similar but distinct events
- Contract monitor `get_logs` pagination for large block ranges
- CLI `trace` command crash when graph has disconnected components

### Added
- `--output csv` flag for CLI trace command
- Rate limit configuration for RPC provider

## [0.4.0] - 2025-05-10

### Added
- DEX monitor for Uniswap V2-style pool events (Swap, Mint, Burn, Sync)
- Wallet clustering module with funding source and co-spending heuristics
- Discord alert handler with embed support
- Generic webhook alert handler
- `Pipeline` class for multi-stage event processing with backpressure
- Docker Compose setup with optional Redis service

### Changed
- Migrated from `setup.py` to `pyproject.toml`
- Supervisor now uses exponential backoff instead of fixed delay
- Increased default max_workers from 500 to 1000

### Removed
- Deprecated `AgentConfig.from_env()` method (use env var overrides instead)

## [0.3.0] - 2025-03-22

### Added
- Pattern matching engine (sandwich attacks, wallet drains, LP pulls)
- Anomaly detection with volume spike and rapid transaction heuristics
- WebSocket provider with auto-reconnect and subscription management
- Mempool monitor for pending transaction analysis
- Telegram alert handler
- YAML configuration with `${ENV_VAR}` interpolation
- CLI commands: `watch`, `trace`, `serve`, `status`

### Changed
- Refactored monitor base class to support both polling and streaming
- Event handlers now receive structured event dicts instead of raw data

## [0.2.0] - 2025-01-15

### Added
- Wallet graph analysis (trace forward/backward, shortest path, clustering)
- Contract monitor with function selector decoding
- RPC provider with connection pooling and batch requests
- Supervisor tree with ONE_FOR_ONE, ONE_FOR_ALL, REST_FOR_ONE strategies
- Alert dispatcher with deduplication

### Changed
- Switched from synchronous to fully async architecture
- Worker processes now report health status to supervisor

## [0.1.0] - 2024-11-02

### Added
- Initial release
- Basic wallet monitor (ETH transfers, balance changes)
- Simple RPC provider
- Console logging
- Click-based CLI skeleton
