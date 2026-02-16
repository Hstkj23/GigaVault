"""Tests for the wallet graph analysis module."""

import pytest

from spawn_agent.analysis.graph import WalletGraph


class TestWalletGraph:
    """Test wallet transaction graph analysis."""

    @pytest.fixture
    def graph_with_data(self):
        graph = WalletGraph()
        transactions = [
            {"from": "0xaaa", "to": "0xbbb", "value": 1000, "hash": "tx1", "blockNumber": 100},
            {"from": "0xbbb", "to": "0xccc", "value": 500, "hash": "tx2", "blockNumber": 101},
            {"from": "0xccc", "to": "0xddd", "value": 200, "hash": "tx3", "blockNumber": 102},
            {"from": "0xaaa", "to": "0xccc", "value": 300, "hash": "tx4", "blockNumber": 103},
            {"from": "0xddd", "to": "0xaaa", "value": 100, "hash": "tx5", "blockNumber": 104},
        ]
        for tx in transactions:
            graph.add_transaction(tx)
        return graph

    def test_empty_graph(self):
        graph = WalletGraph()
        assert graph.node_count == 0
        assert graph.edge_count == 0

    def test_add_transaction(self):
        graph = WalletGraph()
        graph.add_transaction({
            "from": "0xaaa", "to": "0xbbb", "value": 1000,
            "hash": "tx1", "blockNumber": 100,
        })
        assert graph.node_count == 2
        assert graph.edge_count == 1

    def test_node_stats(self, graph_with_data):
        assert graph_with_data.node_count == 4
        assert graph_with_data.edge_count == 5

    def test_trace_forward(self, graph_with_data):
        result = graph_with_data.trace_forward("0xaaa", max_depth=2)
        assert result["address"] == "0xaaa"
        assert len(result["children"]) > 0

    def test_trace_backward(self, graph_with_data):
        result = graph_with_data.trace_backward("0xddd", max_depth=2)
        assert result["address"] == "0xddd"
        assert len(result["children"]) > 0

    def test_trace_depth_limit(self, graph_with_data):
        result = graph_with_data.trace_forward("0xaaa", max_depth=0)
        assert result["children"] == []

    def test_trace_min_value(self, graph_with_data):
        result = graph_with_data.trace_forward("0xaaa", max_depth=3, min_value_wei=400)
        # Should only include edges with value >= 400
        for child in result["children"]:
            if "total_value_wei" in child:
                assert child["total_value_wei"] >= 400

    def test_shortest_path(self, graph_with_data):
        path = graph_with_data.shortest_path("0xaaa", "0xddd")
        assert path is not None
        assert path[0] == "0xaaa"
        assert path[-1] == "0xddd"

    def test_shortest_path_no_path(self):
        graph = WalletGraph()
        graph.add_transaction({
            "from": "0xaaa", "to": "0xbbb", "value": 100,
            "hash": "tx1", "blockNumber": 1,
        })
        path = graph.shortest_path("0xbbb", "0xaaa")
        assert path is None  # No reverse edge

    def test_shortest_path_nonexistent(self, graph_with_data):
        path = graph_with_data.shortest_path("0xaaa", "0xzzz")
        assert path is None

    def test_find_clusters(self, graph_with_data):
        clusters = graph_with_data.find_clusters(min_connections=2)
        assert len(clusters) >= 1
        # All 4 addresses should be in a single connected component
        largest = clusters[0]
        assert len(largest) == 4

    def test_subgraph(self, graph_with_data):
        sub = graph_with_data.subgraph("0xbbb", radius=1)
        assert sub.node_count <= graph_with_data.node_count
        assert sub.edge_count <= graph_with_data.edge_count

    def test_set_label(self, graph_with_data):
        graph_with_data.set_label("0xaaa", "Whale")
        result = graph_with_data.to_dict()
        node_a = next(n for n in result["nodes"] if n["address"] == "0xaaa")
        assert node_a["label"] == "Whale"

    def test_to_dict(self, graph_with_data):
        data = graph_with_data.to_dict()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 4
        assert len(data["edges"]) == 5

    def test_get_stats(self, graph_with_data):
        stats = graph_with_data.get_stats()
        assert stats["nodes"] == 4
        assert stats["edges"] == 5
        assert stats["total_volume_wei"] == 2100

    def test_cycle_detection(self, graph_with_data):
        # 0xaaa -> 0xbbb -> 0xccc -> 0xddd -> 0xaaa forms a cycle
        result = graph_with_data.trace_forward("0xaaa", max_depth=5)
        # Should detect cycle without infinite loop
        assert result is not None
