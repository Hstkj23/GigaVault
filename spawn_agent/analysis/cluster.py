"""
Wallet clustering algorithms.

Groups wallets into clusters based on behavioral similarity,
shared counterparties, temporal correlation, and funding source analysis.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class WalletCluster:
    """A group of related wallet addresses."""

    cluster_id: int
    addresses: set[str] = field(default_factory=set)
    funding_sources: set[str] = field(default_factory=set)
    common_targets: set[str] = field(default_factory=set)
    confidence: float = 0.0
    label: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "addresses": sorted(self.addresses),
            "size": len(self.addresses),
            "funding_sources": sorted(self.funding_sources),
            "common_targets": sorted(self.common_targets),
            "confidence": self.confidence,
            "label": self.label,
        }


class WalletClusterer:
    """
    Cluster wallets based on on-chain behavior.

    Uses multiple heuristics:
        1. **Funding source**: Wallets funded by the same source
        2. **Co-spending**: Wallets that interact with the same contracts
        3. **Temporal**: Wallets active in similar time windows
        4. **Value fingerprint**: Wallets transacting similar amounts

    Args:
        min_shared_targets: Minimum shared counterparties for co-spending clustering.
        time_window: Window in seconds for temporal correlation.
        min_cluster_size: Minimum addresses to form a cluster.
    """

    def __init__(
        self,
        min_shared_targets: int = 3,
        time_window: float = 300.0,
        min_cluster_size: int = 2,
    ) -> None:
        self.min_shared_targets = min_shared_targets
        self.time_window = time_window
        self.min_cluster_size = min_cluster_size

        self._funding_map: dict[str, str] = {}  # address -> funder
        self._target_map: dict[str, set[str]] = defaultdict(set)  # address -> targets
        self._timestamp_map: dict[str, list[float]] = defaultdict(list)

    def add_transaction(self, tx: dict[str, Any]) -> None:
        """Record a transaction for clustering analysis."""
        from_addr = tx.get("from", "").lower()
        to_addr = tx.get("to", "").lower()
        timestamp = tx.get("timestamp", 0)

        if not from_addr or not to_addr:
            return

        # Track funding relationships
        value = int(tx.get("value", 0))
        if value > 0 and to_addr not in self._funding_map:
            self._funding_map[to_addr] = from_addr

        # Track target interactions
        self._target_map[from_addr].add(to_addr)

        # Track activity timestamps
        self._timestamp_map[from_addr].append(timestamp)

    def cluster_by_funding(self) -> list[WalletCluster]:
        """Cluster wallets by common funding source."""
        # Group addresses by their first funder
        funder_groups: dict[str, set[str]] = defaultdict(set)
        for address, funder in self._funding_map.items():
            funder_groups[funder].add(address)

        clusters = []
        for idx, (funder, addresses) in enumerate(funder_groups.items()):
            if len(addresses) >= self.min_cluster_size:
                clusters.append(
                    WalletCluster(
                        cluster_id=idx,
                        addresses=addresses,
                        funding_sources={funder},
                        confidence=min(0.9, 0.3 + len(addresses) * 0.1),
                        label=f"Funded by {funder[:10]}...",
                    )
                )

        return sorted(clusters, key=lambda c: len(c.addresses), reverse=True)

    def cluster_by_cospending(self) -> list[WalletCluster]:
        """Cluster wallets that interact with the same contracts."""
        # Find pairs of addresses with enough shared targets
        addresses = list(self._target_map.keys())
        clusters: list[WalletCluster] = []
        used: set[str] = set()
        cluster_id = 0

        for i in range(len(addresses)):
            if addresses[i] in used:
                continue

            cluster_members = {addresses[i]}
            common = set(self._target_map[addresses[i]])

            for j in range(i + 1, len(addresses)):
                if addresses[j] in used:
                    continue

                shared = self._target_map[addresses[i]] & self._target_map[addresses[j]]
                if len(shared) >= self.min_shared_targets:
                    cluster_members.add(addresses[j])
                    common &= self._target_map[addresses[j]]

            if len(cluster_members) >= self.min_cluster_size:
                used.update(cluster_members)
                clusters.append(
                    WalletCluster(
                        cluster_id=cluster_id,
                        addresses=cluster_members,
                        common_targets=common,
                        confidence=min(
                            0.85, 0.4 + len(common) * 0.05 + len(cluster_members) * 0.05
                        ),
                        label=f"Co-spending cluster ({len(common)} shared targets)",
                    )
                )
                cluster_id += 1

        return sorted(clusters, key=lambda c: len(c.addresses), reverse=True)

    def cluster_by_temporal(self) -> list[WalletCluster]:
        """Cluster wallets active in similar time windows."""
        addresses = list(self._timestamp_map.keys())
        clusters: list[WalletCluster] = []
        used: set[str] = set()
        cluster_id = 0

        for i in range(len(addresses)):
            if addresses[i] in used:
                continue

            times_i = set(
                int(t / self.time_window) for t in self._timestamp_map[addresses[i]]
            )
            cluster_members = {addresses[i]}

            for j in range(i + 1, len(addresses)):
                if addresses[j] in used:
                    continue

                times_j = set(
                    int(t / self.time_window)
                    for t in self._timestamp_map[addresses[j]]
                )
                overlap = len(times_i & times_j)
                total = len(times_i | times_j)

                if total > 0 and overlap / total > 0.5:
                    cluster_members.add(addresses[j])

            if len(cluster_members) >= self.min_cluster_size:
                used.update(cluster_members)
                clusters.append(
                    WalletCluster(
                        cluster_id=cluster_id,
                        addresses=cluster_members,
                        confidence=0.5,
                        label=f"Temporal cluster",
                    )
                )
                cluster_id += 1

        return clusters

    def find_all_clusters(self) -> list[WalletCluster]:
        """Run all clustering algorithms and merge results."""
        funding = self.cluster_by_funding()
        cospending = self.cluster_by_cospending()
        temporal = self.cluster_by_temporal()

        # Merge overlapping clusters
        all_clusters = funding + cospending + temporal
        return self._merge_overlapping(all_clusters)

    def _merge_overlapping(
        self, clusters: list[WalletCluster]
    ) -> list[WalletCluster]:
        """Merge clusters that share addresses."""
        if not clusters:
            return []

        merged: list[WalletCluster] = []
        used_indices: set[int] = set()

        for i, c1 in enumerate(clusters):
            if i in used_indices:
                continue

            merged_cluster = WalletCluster(
                cluster_id=len(merged),
                addresses=set(c1.addresses),
                funding_sources=set(c1.funding_sources),
                common_targets=set(c1.common_targets),
                confidence=c1.confidence,
            )

            for j in range(i + 1, len(clusters)):
                if j in used_indices:
                    continue

                c2 = clusters[j]
                overlap = merged_cluster.addresses & c2.addresses
                if overlap:
                    merged_cluster.addresses |= c2.addresses
                    merged_cluster.funding_sources |= c2.funding_sources
                    merged_cluster.common_targets |= c2.common_targets
                    merged_cluster.confidence = max(
                        merged_cluster.confidence, c2.confidence
                    )
                    used_indices.add(j)

            if len(merged_cluster.addresses) >= self.min_cluster_size:
                merged.append(merged_cluster)
            used_indices.add(i)

        return sorted(merged, key=lambda c: len(c.addresses), reverse=True)

    def reset(self) -> None:
        """Reset all clustering data."""
        self._funding_map.clear()
        self._target_map.clear()
        self._timestamp_map.clear()
