"""
Anomaly detection for on-chain transaction streams.

Implements statistical and heuristic-based anomaly detection across
multiple dimensions: volume, timing, counterparty behavior, and
coordinated wallet activity.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    """Classification of anomaly types."""

    VOLUME_SPIKE = "volume_spike"
    RAPID_TRANSACTIONS = "rapid_transactions"
    WASH_TRADING = "wash_trading"
    COORDINATED_ACTIVITY = "coordinated_activity"
    NEW_WALLET_PATTERN = "new_wallet_pattern"
    UNUSUAL_GAS = "unusual_gas"
    CIRCULAR_FLOW = "circular_flow"


@dataclass
class Anomaly:
    """Detected anomaly with metadata."""

    anomaly_type: AnomalyType
    severity: float  # 0.0 to 1.0
    address: str
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.anomaly_type.value,
            "severity": self.severity,
            "address": self.address,
            "description": self.description,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
        }


class AnomalyDetector:
    """
    Stateful anomaly detector for transaction streams.

    Maintains rolling windows of transaction history per address
    and applies multiple detection heuristics to identify unusual
    patterns.

    Args:
        volume_window: Window size in seconds for volume baseline.
        volume_threshold: Multiplier above baseline to trigger volume anomaly.
        rapid_tx_threshold: Number of transactions in 60s to trigger rapid tx anomaly.
        circular_max_hops: Maximum hops to check for circular fund flows.
    """

    def __init__(
        self,
        volume_window: float = 3600.0,
        volume_threshold: float = 5.0,
        rapid_tx_threshold: int = 10,
        circular_max_hops: int = 4,
    ) -> None:
        self.volume_window = volume_window
        self.volume_threshold = volume_threshold
        self.rapid_tx_threshold = rapid_tx_threshold
        self.circular_max_hops = circular_max_hops

        # Rolling transaction history per address
        self._tx_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=10000)
        )
        # Volume baselines
        self._volume_baselines: dict[str, float] = {}
        # Recent transfers for circular flow detection
        self._recent_transfers: deque = deque(maxlen=50000)
        # Known wallet ages (address -> first_seen timestamp)
        self._wallet_ages: dict[str, float] = {}

    def analyze(self, event: dict[str, Any]) -> list[Anomaly]:
        """
        Analyze an event and return any detected anomalies.

        Args:
            event: Transaction or transfer event dictionary.

        Returns:
            List of detected anomalies (may be empty).
        """
        anomalies: list[Anomaly] = []
        address = event.get("address", event.get("from_address", "")).lower()
        now = time.time()

        if not address:
            return anomalies

        # Record the transaction
        tx_record = {
            "timestamp": now,
            "value": event.get("value_wei", event.get("value_raw", 0)),
            "from": event.get("from_address", "").lower(),
            "to": event.get("to_address", "").lower(),
            "type": event.get("type", "unknown"),
        }
        self._tx_history[address].append(tx_record)
        self._recent_transfers.append(tx_record)

        # Track wallet age
        if address not in self._wallet_ages:
            self._wallet_ages[address] = now

        # Run detectors
        volume_anomaly = self._detect_volume_spike(address, tx_record)
        if volume_anomaly:
            anomalies.append(volume_anomaly)

        rapid_anomaly = self._detect_rapid_transactions(address)
        if rapid_anomaly:
            anomalies.append(rapid_anomaly)

        new_wallet = self._detect_new_wallet_pattern(address, tx_record)
        if new_wallet:
            anomalies.append(new_wallet)

        gas_anomaly = self._detect_unusual_gas(address, event)
        if gas_anomaly:
            anomalies.append(gas_anomaly)

        if anomalies:
            logger.info(
                "Detected %d anomalies for %s: %s",
                len(anomalies),
                address[:10],
                [a.anomaly_type.value for a in anomalies],
            )

        return anomalies

    def detect_circular_flows(
        self, window_seconds: float = 600.0
    ) -> list[Anomaly]:
        """
        Scan recent transfers for circular fund flows.

        Checks if funds sent from address A return to A within
        ``circular_max_hops`` transfers and ``window_seconds``.
        """
        cutoff = time.time() - window_seconds
        recent = [t for t in self._recent_transfers if t["timestamp"] > cutoff]

        # Build a simple directed graph from recent transfers
        graph: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for t in recent:
            if t["from"] and t["to"]:
                graph[t["from"]].append((t["to"], t["value"]))

        anomalies: list[Anomaly] = []
        checked: set[str] = set()

        for start_addr in graph:
            if start_addr in checked:
                continue

            # BFS to find cycles
            cycle = self._find_cycle(graph, start_addr, self.circular_max_hops)
            if cycle:
                checked.update(cycle)
                total_value = sum(
                    t["value"]
                    for t in recent
                    if t["from"] in cycle and t["to"] in cycle
                )
                anomalies.append(
                    Anomaly(
                        anomaly_type=AnomalyType.CIRCULAR_FLOW,
                        severity=min(0.9, len(cycle) * 0.2),
                        address=start_addr,
                        description=(
                            f"Circular fund flow detected involving "
                            f"{len(cycle)} addresses"
                        ),
                        evidence={
                            "cycle_addresses": list(cycle),
                            "total_value_wei": total_value,
                            "hop_count": len(cycle),
                        },
                    )
                )

        return anomalies

    def detect_coordinated_activity(
        self,
        addresses: list[str],
        time_window: float = 120.0,
        min_group_size: int = 3,
    ) -> list[Anomaly]:
        """
        Detect coordinated activity across a group of addresses.

        Looks for multiple addresses performing similar actions within
        a narrow time window.
        """
        now = time.time()
        cutoff = now - time_window
        anomalies: list[Anomaly] = []

        # Group recent transactions by target address
        target_groups: dict[str, list[dict]] = defaultdict(list)

        for addr in addresses:
            for tx in self._tx_history.get(addr.lower(), []):
                if tx["timestamp"] > cutoff and tx["to"]:
                    target_groups[tx["to"]].append(
                        {**tx, "source_address": addr.lower()}
                    )

        # Check for convergence on the same target
        for target, txs in target_groups.items():
            unique_senders = set(t["source_address"] for t in txs)
            if len(unique_senders) >= min_group_size:
                anomalies.append(
                    Anomaly(
                        anomaly_type=AnomalyType.COORDINATED_ACTIVITY,
                        severity=min(1.0, len(unique_senders) * 0.15),
                        address=target,
                        description=(
                            f"{len(unique_senders)} addresses interacted with "
                            f"{target[:10]}... within {time_window}s"
                        ),
                        evidence={
                            "target": target,
                            "senders": list(unique_senders),
                            "tx_count": len(txs),
                            "window_seconds": time_window,
                        },
                    )
                )

        return anomalies

    def _detect_volume_spike(
        self, address: str, tx_record: dict
    ) -> Optional[Anomaly]:
        """Detect if current transaction volume exceeds the baseline."""
        history = self._tx_history[address]
        now = tx_record["timestamp"]
        cutoff = now - self.volume_window

        recent_volume = sum(
            t["value"] for t in history if t["timestamp"] > cutoff
        )

        baseline = self._volume_baselines.get(address)
        if baseline is None:
            # Need at least some history before detecting spikes
            if len(history) >= 5:
                self._volume_baselines[address] = recent_volume / max(
                    1, len([t for t in history if t["timestamp"] > cutoff])
                )
            return None

        if baseline > 0 and recent_volume > baseline * self.volume_threshold:
            severity = min(1.0, (recent_volume / baseline - 1) / 10)
            # Update baseline with exponential moving average
            self._volume_baselines[address] = baseline * 0.9 + recent_volume * 0.1
            return Anomaly(
                anomaly_type=AnomalyType.VOLUME_SPIKE,
                severity=severity,
                address=address,
                description=(
                    f"Volume spike: {recent_volume / baseline:.1f}x above "
                    f"baseline in last {self.volume_window / 60:.0f}min"
                ),
                evidence={
                    "recent_volume": recent_volume,
                    "baseline": baseline,
                    "multiplier": recent_volume / baseline,
                },
            )

        # Slowly update baseline
        self._volume_baselines[address] = baseline * 0.95 + recent_volume * 0.05
        return None

    def _detect_rapid_transactions(self, address: str) -> Optional[Anomaly]:
        """Detect unusually rapid transaction frequency."""
        history = self._tx_history[address]
        now = time.time()
        last_minute = [t for t in history if now - t["timestamp"] < 60]

        if len(last_minute) >= self.rapid_tx_threshold:
            return Anomaly(
                anomaly_type=AnomalyType.RAPID_TRANSACTIONS,
                severity=min(1.0, len(last_minute) / (self.rapid_tx_threshold * 2)),
                address=address,
                description=(
                    f"{len(last_minute)} transactions in the last 60 seconds"
                ),
                evidence={
                    "tx_count_60s": len(last_minute),
                    "threshold": self.rapid_tx_threshold,
                },
            )
        return None

    def _detect_new_wallet_pattern(
        self, address: str, tx_record: dict
    ) -> Optional[Anomaly]:
        """Detect suspicious patterns from newly created wallets."""
        wallet_age = time.time() - self._wallet_ages.get(address, time.time())

        # Only flag wallets seen less than 1 hour ago
        if wallet_age > 3600:
            return None

        history = self._tx_history[address]
        if len(history) < 3:
            return None

        # New wallet with high transaction count
        tx_rate = len(history) / max(wallet_age, 1)
        if tx_rate > 0.1:  # More than 1 tx per 10 seconds
            return Anomaly(
                anomaly_type=AnomalyType.NEW_WALLET_PATTERN,
                severity=min(0.8, tx_rate),
                address=address,
                description=(
                    f"New wallet ({wallet_age:.0f}s old) with high activity: "
                    f"{len(history)} transactions"
                ),
                evidence={
                    "wallet_age_seconds": wallet_age,
                    "tx_count": len(history),
                    "tx_rate_per_second": tx_rate,
                },
            )
        return None

    def _detect_unusual_gas(
        self, address: str, event: dict[str, Any]
    ) -> Optional[Anomaly]:
        """Detect transactions with unusually high gas prices."""
        gas_price = event.get("gas_price")
        max_priority = event.get("max_priority_fee")

        if gas_price is None and max_priority is None:
            return None

        # Flag extremely high priority fees (potential MEV)
        if max_priority and max_priority > 100 * 10**9:  # > 100 gwei
            return Anomaly(
                anomaly_type=AnomalyType.UNUSUAL_GAS,
                severity=0.6,
                address=address,
                description=(
                    f"High priority fee: {max_priority / 10**9:.1f} gwei"
                ),
                evidence={
                    "max_priority_fee_wei": max_priority,
                    "max_priority_fee_gwei": max_priority / 10**9,
                },
            )
        return None

    @staticmethod
    def _find_cycle(
        graph: dict[str, list[tuple[str, int]]],
        start: str,
        max_hops: int,
    ) -> Optional[set[str]]:
        """Find a cycle starting and ending at the given address."""
        from collections import deque

        queue: deque[list[str]] = deque([[start]])

        while queue:
            path = queue.popleft()
            if len(path) > max_hops + 1:
                continue

            current = path[-1]
            for neighbor, _ in graph.get(current, []):
                if neighbor == start and len(path) > 2:
                    return set(path)
                if neighbor not in path:
                    queue.append(path + [neighbor])

        return None

    def reset(self, address: Optional[str] = None) -> None:
        """Reset detector state for an address or all addresses."""
        if address:
            address = address.lower()
            self._tx_history.pop(address, None)
            self._volume_baselines.pop(address, None)
            self._wallet_ages.pop(address, None)
        else:
            self._tx_history.clear()
            self._volume_baselines.clear()
            self._recent_transfers.clear()
            self._wallet_ages.clear()
