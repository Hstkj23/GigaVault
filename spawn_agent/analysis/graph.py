"""
Wallet graph construction and analysis.

Builds directed transaction graphs from on-chain data and provides
algorithms for tracing fund flows, clustering related wallets,
and identifying patterns in wallet relationships.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class GraphEdge:
    """An edge in the wallet transaction graph."""

    from_address: str
    to_address: str
    value_wei: int
    tx_hash: str
    block_number: int
    timestamp: Optional[int] = None


@dataclass
class GraphNode:
    """A node (address) in the wallet transaction graph."""

    address: str
    label: Optional[str] = None
    is_contract: bool = False
    total_in: int = 0
    total_out: int = 0
    tx_count: int = 0
    first_seen: Optional[int] = None
    last_seen: Optional[int] = None


class WalletGraph:
    """
    Directed transaction graph for wallet analysis.

    Supports:
        - Fund flow tracing (forward and backward)
        - Wallet clustering via co-spending heuristics
        - Shortest path between addresses
        - Subgraph extraction around a target address

    Example::

        graph = WalletGraph()
        graph.add_transaction(tx_data)

        # Trace where funds went (3 hops)
        flow = graph.trace_forward("0xabc...", max_depth=3)

        # Find clusters of related wallets
        clusters = graph.find_clusters()
    """

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._adjacency: dict[str, list[int]] = defaultdict(list)
        self._reverse_adjacency: dict[str, list[int]] = defaultdict(list)

    def add_transaction(self, tx: dict[str, Any]) -> None:
        """Add a transaction to the graph."""
        from_addr = tx.get("from", "").lower()
        to_addr = tx.get("to", "").lower()
        value_wei = int(tx.get("value", 0))
        block = tx.get("blockNumber", 0)

        if not from_addr or not to_addr:
            return

        # Update or create nodes
        self._ensure_node(from_addr, block)
        self._ensure_node(to_addr, block)

        self._nodes[from_addr].total_out += value_wei
        self._nodes[from_addr].tx_count += 1
        self._nodes[to_addr].total_in += value_wei
        self._nodes[to_addr].tx_count += 1

        # Create edge
        edge = GraphEdge(
            from_address=from_addr,
            to_address=to_addr,
            value_wei=value_wei,
            tx_hash=tx.get("hash", ""),
            block_number=block,
            timestamp=tx.get("timestamp"),
        )

        edge_idx = len(self._edges)
        self._edges.append(edge)
        self._adjacency[from_addr].append(edge_idx)
        self._reverse_adjacency[to_addr].append(edge_idx)

    def _ensure_node(self, address: str, block: int) -> None:
        """Create a node if it doesn't exist, or update seen times."""
        if address not in self._nodes:
            self._nodes[address] = GraphNode(
                address=address,
                first_seen=block,
                last_seen=block,
            )
        else:
            node = self._nodes[address]
            if node.first_seen is None or block < node.first_seen:
                node.first_seen = block
            if node.last_seen is None or block > node.last_seen:
                node.last_seen = block

    def trace_forward(
        self,
        address: str,
        max_depth: int = 3,
        min_value_wei: int = 0,
    ) -> dict[str, Any]:
        """
        Trace fund flows forward from an address.

        Returns a tree structure showing where funds went, up to
        ``max_depth`` hops from the source address.
        """
        address = address.lower()
        visited: set[str] = set()
        return self._trace_recursive(
            address, max_depth, min_value_wei, visited, direction="forward"
        )

    def trace_backward(
        self,
        address: str,
        max_depth: int = 3,
        min_value_wei: int = 0,
    ) -> dict[str, Any]:
        """
        Trace fund flows backward to find the source of funds.

        Returns a tree structure showing where funds came from, up to
        ``max_depth`` hops from the target address.
        """
        address = address.lower()
        visited: set[str] = set()
        return self._trace_recursive(
            address, max_depth, min_value_wei, visited, direction="backward"
        )

    def _trace_recursive(
        self,
        address: str,
        depth: int,
        min_value_wei: int,
        visited: set[str],
        direction: str,
    ) -> dict[str, Any]:
        """Recursive DFS traversal for fund flow tracing."""
        visited.add(address)
        node = self._nodes.get(address)

        result: dict[str, Any] = {
            "address": address,
            "label": node.label if node else None,
            "total_in": node.total_in if node else 0,
            "total_out": node.total_out if node else 0,
            "children": [],
        }

        if depth <= 0:
            return result

        if direction == "forward":
            edge_indices = self._adjacency.get(address, [])
        else:
            edge_indices = self._reverse_adjacency.get(address, [])

        # Aggregate by target/source address
        aggregated: dict[str, int] = defaultdict(int)
        edge_refs: dict[str, list[GraphEdge]] = defaultdict(list)

        for idx in edge_indices:
            edge = self._edges[idx]
            if edge.value_wei < min_value_wei:
                continue
            target = edge.to_address if direction == "forward" else edge.from_address
            aggregated[target] += edge.value_wei
            edge_refs[target].append(edge)

        # Sort by total value (largest first)
        sorted_targets = sorted(aggregated.items(), key=lambda x: -x[1])

        for target_addr, total_value in sorted_targets:
            if target_addr in visited:
                result["children"].append(
                    {
                        "address": target_addr,
                        "total_value_wei": total_value,
                        "tx_count": len(edge_refs[target_addr]),
                        "cycle": True,
                    }
                )
                continue

            child = self._trace_recursive(
                target_addr, depth - 1, min_value_wei, visited, direction
            )
            child["total_value_wei"] = total_value
            child["tx_count"] = len(edge_refs[target_addr])
            result["children"].append(child)

        return result

    def find_clusters(self, min_connections: int = 2) -> list[set[str]]:
        """
        Find clusters of related wallets using connected components.

        Two wallets are considered related if they have bidirectional
        transfers or share common counterparties beyond a threshold.

        Args:
            min_connections: Minimum shared connections to form a cluster.

        Returns:
            List of address sets, each representing a cluster.
        """
        # Build undirected adjacency for clustering
        undirected: dict[str, set[str]] = defaultdict(set)

        for edge in self._edges:
            undirected[edge.from_address].add(edge.to_address)
            undirected[edge.to_address].add(edge.from_address)

        # Find connected components via BFS
        visited: set[str] = set()
        clusters: list[set[str]] = []

        for address in self._nodes:
            if address in visited:
                continue

            cluster: set[str] = set()
            queue = deque([address])

            while queue:
                current = queue.popleft()
                if current in visited:
                    continue
                visited.add(current)
                cluster.add(current)

                for neighbor in undirected.get(current, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)

            if len(cluster) >= min_connections:
                clusters.append(cluster)

        return sorted(clusters, key=len, reverse=True)

    def shortest_path(
        self, from_address: str, to_address: str
    ) -> Optional[list[str]]:
        """
        Find the shortest path between two addresses.

        Returns a list of addresses forming the shortest path, or None
        if no path exists.
        """
        from_address = from_address.lower()
        to_address = to_address.lower()

        if from_address not in self._nodes or to_address not in self._nodes:
            return None

        visited: set[str] = set()
        queue: deque[list[str]] = deque([[from_address]])

        while queue:
            path = queue.popleft()
            current = path[-1]

            if current == to_address:
                return path

            if current in visited:
                continue
            visited.add(current)

            for edge_idx in self._adjacency.get(current, []):
                edge = self._edges[edge_idx]
                if edge.to_address not in visited:
                    queue.append(path + [edge.to_address])

        return None

    def subgraph(self, center: str, radius: int = 2) -> WalletGraph:
        """Extract a subgraph around a center address within the given radius."""
        center = center.lower()
        relevant_addresses: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(center, 0)])

        while queue:
            addr, depth = queue.popleft()
            if addr in relevant_addresses or depth > radius:
                continue
            relevant_addresses.add(addr)

            for idx in self._adjacency.get(addr, []):
                queue.append((self._edges[idx].to_address, depth + 1))
            for idx in self._reverse_adjacency.get(addr, []):
                queue.append((self._edges[idx].from_address, depth + 1))

        sub = WalletGraph()
        for edge in self._edges:
            if edge.from_address in relevant_addresses and edge.to_address in relevant_addresses:
                sub._edges.append(edge)
                sub._ensure_node(edge.from_address, edge.block_number)
                sub._ensure_node(edge.to_address, edge.block_number)
                idx = len(sub._edges) - 1
                sub._adjacency[edge.from_address].append(idx)
                sub._reverse_adjacency[edge.to_address].append(idx)

        return sub

    def set_label(self, address: str, label: str) -> None:
        """Set a label for an address node."""
        address = address.lower()
        if address in self._nodes:
            self._nodes[address].label = label

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        return {
            "nodes": self.node_count,
            "edges": self.edge_count,
            "total_volume_wei": sum(e.value_wei for e in self._edges),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize the graph to a dictionary."""
        return {
            "nodes": [
                {
                    "address": n.address,
                    "label": n.label,
                    "is_contract": n.is_contract,
                    "total_in": n.total_in,
                    "total_out": n.total_out,
                    "tx_count": n.tx_count,
                }
                for n in self._nodes.values()
            ],
            "edges": [
                {
                    "from": e.from_address,
                    "to": e.to_address,
                    "value_wei": e.value_wei,
                    "tx_hash": e.tx_hash,
                    "block_number": e.block_number,
                }
                for e in self._edges
            ],
        }
