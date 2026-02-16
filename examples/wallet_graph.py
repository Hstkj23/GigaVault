#!/usr/bin/env python3
"""
Wallet graph analysis example.

Demonstrates how to build a transaction graph and trace fund flows
between wallets using SpawnAgent's graph analysis module.
"""

import json
import os

from spawn_agent.analysis.graph import WalletGraph


def main():
    graph = WalletGraph()

    # --- Simulate transaction data ---
    # In production, you would fetch this from an RPC provider or indexer.

    transactions = [
        {
            "from": "0xaaaa1111000000000000000000000000deadbeef",
            "to": "0xbbbb2222000000000000000000000000deadbeef",
            "value": 50_000_000_000_000_000_000,  # 50 ETH
            "hash": "0x0001",
            "blockNumber": 18000001,
        },
        {
            "from": "0xbbbb2222000000000000000000000000deadbeef",
            "to": "0xcccc3333000000000000000000000000deadbeef",
            "value": 30_000_000_000_000_000_000,  # 30 ETH
            "hash": "0x0002",
            "blockNumber": 18000010,
        },
        {
            "from": "0xbbbb2222000000000000000000000000deadbeef",
            "to": "0xdddd4444000000000000000000000000deadbeef",
            "value": 18_000_000_000_000_000_000,  # 18 ETH
            "hash": "0x0003",
            "blockNumber": 18000020,
        },
        {
            "from": "0xcccc3333000000000000000000000000deadbeef",
            "to": "0xeeee5555000000000000000000000000deadbeef",
            "value": 25_000_000_000_000_000_000,  # 25 ETH
            "hash": "0x0004",
            "blockNumber": 18000030,
        },
        {
            "from": "0xdddd4444000000000000000000000000deadbeef",
            "to": "0xeeee5555000000000000000000000000deadbeef",
            "value": 15_000_000_000_000_000_000,  # 15 ETH
            "hash": "0x0005",
            "blockNumber": 18000040,
        },
        {
            "from": "0xeeee5555000000000000000000000000deadbeef",
            "to": "0xaaaa1111000000000000000000000000deadbeef",
            "value": 5_000_000_000_000_000_000,  # 5 ETH (circular)
            "hash": "0x0006",
            "blockNumber": 18000050,
        },
    ]

    # Build the graph
    for tx in transactions:
        graph.add_transaction(tx)

    # Add labels
    graph.set_label("0xaaaa1111000000000000000000000000deadbeef", "Source Wallet")
    graph.set_label("0xbbbb2222000000000000000000000000deadbeef", "Intermediary A")
    graph.set_label("0xcccc3333000000000000000000000000deadbeef", "Intermediary B")
    graph.set_label("0xdddd4444000000000000000000000000deadbeef", "Intermediary C")
    graph.set_label("0xeeee5555000000000000000000000000deadbeef", "Consolidation")

    # --- Analysis ---

    print("=== Graph Statistics ===")
    stats = graph.get_stats()
    print(f"Nodes: {stats['nodes']}")
    print(f"Edges: {stats['edges']}")
    print(f"Total volume: {stats['total_volume_wei'] / 1e18:.2f} ETH")
    print()

    # Trace forward from source
    print("=== Forward Trace from Source ===")
    trace = graph.trace_forward(
        "0xaaaa1111000000000000000000000000deadbeef",
        max_depth=3,
    )
    print(json.dumps(trace, indent=2, default=str))
    print()

    # Shortest path
    print("=== Shortest Path: Source → Consolidation ===")
    path = graph.shortest_path(
        "0xaaaa1111000000000000000000000000deadbeef",
        "0xeeee5555000000000000000000000000deadbeef",
    )
    if path:
        print(" → ".join(path))
    else:
        print("No path found")
    print()

    # Find clusters
    print("=== Clusters ===")
    clusters = graph.find_clusters(min_connections=1)
    for i, cluster in enumerate(clusters):
        print(f"Cluster {i + 1}: {len(cluster)} addresses")
        for addr in cluster:
            print(f"  - {addr}")


if __name__ == "__main__":
    main()
