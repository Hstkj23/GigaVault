"""Tests for the pattern matching module."""

import pytest

from spawn_agent.analysis.patterns import PatternMatcher, PatternType


class TestPatternMatcher:
    """Test on-chain pattern detection."""

    def test_init(self):
        matcher = PatternMatcher()
        assert matcher.window_size == 5000
        assert matcher.min_confidence == 0.5

    def test_ingest_single_tx(self):
        matcher = PatternMatcher()
        matches = matcher.ingest({
            "hash": "0xabc",
            "from": "0xaaa",
            "to": "0xbbb",
            "value": 1000,
            "blockNumber": 100,
            "input": "0x",
        })
        assert isinstance(matches, list)

    def test_wallet_drain_detection(self):
        matcher = PatternMatcher(min_confidence=0.3)
        drainer = "0x" + "a" * 40

        # Simulate many outgoing, no incoming
        matches = []
        for i in range(8):
            result = matcher.ingest({
                "hash": f"0x{i:064x}",
                "from": drainer,
                "to": f"0x{i:040x}",
                "value": 10000000000000000000,  # 10 ETH
                "blockNumber": 100 + i,
                "input": "0x",
            })
            matches.extend(result)

        drain_matches = [
            m for m in matches if m.pattern_type == PatternType.WALLET_DRAIN
        ]
        assert len(drain_matches) >= 1

    def test_lp_pull_detection(self):
        matcher = PatternMatcher(min_confidence=0.3)
        matches = matcher.ingest({
            "hash": "0xdef",
            "from": "0x" + "a" * 40,
            "to": "0x" + "b" * 40,
            "value": 0,
            "blockNumber": 200,
            "input": "0xbaa2abde" + "0" * 200,  # removeLiquidity
        })
        lp_matches = [m for m in matches if m.pattern_type == PatternType.LP_PULL]
        assert len(lp_matches) == 1

    def test_pattern_match_serialization(self):
        matcher = PatternMatcher(min_confidence=0.3)
        matches = matcher.ingest({
            "hash": "0xdef",
            "from": "0x" + "a" * 40,
            "to": "0x" + "b" * 40,
            "value": 0,
            "blockNumber": 200,
            "input": "0xbaa2abde" + "0" * 200,
        })

        for match in matches:
            d = match.to_dict()
            assert "pattern" in d
            assert "confidence" in d
            assert "addresses" in d
            assert "description" in d

    def test_buffer_pruning(self):
        matcher = PatternMatcher(window_size=10)
        for i in range(20):
            matcher.ingest({
                "hash": f"0x{i:064x}",
                "from": "0x" + "a" * 40,
                "to": "0x" + "b" * 40,
                "value": 100,
                "blockNumber": i,
                "input": "0x",
            })
        assert len(matcher._buffer) <= 10

    def test_scan_buffer(self):
        matcher = PatternMatcher()
        for i in range(10):
            matcher.ingest({
                "hash": f"0x{i:064x}",
                "from": "0x" + "a" * 40,
                "to": "0x" + "b" * 40,
                "value": 100,
                "blockNumber": 100,
                "input": "0x",
            })
        results = matcher.scan_buffer()
        assert isinstance(results, list)

    def test_clear(self):
        matcher = PatternMatcher()
        matcher.ingest({"hash": "0x1", "from": "0xa", "to": "0xb", "value": 1, "blockNumber": 1, "input": "0x"})
        matcher.clear()
        assert len(matcher._buffer) == 0
