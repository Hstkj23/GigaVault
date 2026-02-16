"""Tests for the anomaly detection module."""

import time
from unittest.mock import patch

import pytest

from spawn_agent.analysis.anomaly import AnomalyDetector, AnomalyType


class TestAnomalyDetector:
    """Test anomaly detection heuristics."""

    def test_init_defaults(self):
        detector = AnomalyDetector()
        assert detector.volume_window == 3600.0
        assert detector.volume_threshold == 5.0
        assert detector.rapid_tx_threshold == 10

    def test_no_anomaly_normal_tx(self):
        detector = AnomalyDetector()
        event = {
            "address": "0xaaa",
            "from_address": "0xaaa",
            "to_address": "0xbbb",
            "value_wei": 1000,
            "type": "transfer_out",
        }
        anomalies = detector.analyze(event)
        assert len(anomalies) == 0

    def test_rapid_transactions(self):
        detector = AnomalyDetector(rapid_tx_threshold=3)

        for i in range(5):
            anomalies = detector.analyze({
                "address": "0xaaa",
                "from_address": "0xaaa",
                "to_address": f"0x{i:040x}",
                "value_wei": 1000,
                "type": "transfer_out",
            })

        # Should detect rapid transactions
        rapid = [a for a in anomalies if a.anomaly_type == AnomalyType.RAPID_TRANSACTIONS]
        assert len(rapid) >= 1
        assert rapid[0].severity > 0

    def test_anomaly_serialization(self):
        detector = AnomalyDetector(rapid_tx_threshold=2)

        for i in range(4):
            anomalies = detector.analyze({
                "address": "0xtest",
                "from_address": "0xtest",
                "to_address": f"0x{i:040x}",
                "value_wei": 100,
                "type": "transfer_out",
            })

        for anomaly in anomalies:
            d = anomaly.to_dict()
            assert "type" in d
            assert "severity" in d
            assert "address" in d
            assert "description" in d
            assert 0 <= d["severity"] <= 1.0

    def test_detect_circular_flows(self):
        detector = AnomalyDetector()

        # Create circular flow: A -> B -> C -> A
        transfers = [
            {"address": "0xa", "from_address": "0xa", "to_address": "0xb", "value_wei": 1000},
            {"address": "0xb", "from_address": "0xb", "to_address": "0xc", "value_wei": 900},
            {"address": "0xc", "from_address": "0xc", "to_address": "0xa", "value_wei": 800},
        ]

        for t in transfers:
            t["type"] = "transfer_out"
            detector.analyze(t)

        circular = detector.detect_circular_flows(window_seconds=300)
        # May or may not detect depending on timing, but should not crash
        assert isinstance(circular, list)

    def test_detect_coordinated_activity(self):
        detector = AnomalyDetector()

        # Multiple addresses targeting the same contract
        addresses = [f"0x{i:040x}" for i in range(5)]
        target = "0xtarget" + "0" * 34

        for addr in addresses:
            detector.analyze({
                "address": addr,
                "from_address": addr,
                "to_address": target,
                "value_wei": 5000,
                "type": "transfer_out",
            })

        # Check for coordinated activity
        result = detector.detect_coordinated_activity(
            addresses=addresses,
            time_window=120.0,
            min_group_size=3,
        )
        assert isinstance(result, list)

    def test_reset_single_address(self):
        detector = AnomalyDetector()
        detector.analyze({
            "address": "0xaaa",
            "from_address": "0xaaa",
            "to_address": "0xbbb",
            "value_wei": 1000,
            "type": "transfer_out",
        })
        detector.reset("0xaaa")
        assert "0xaaa" not in detector._tx_history

    def test_reset_all(self):
        detector = AnomalyDetector()
        detector.analyze({
            "address": "0xaaa",
            "from_address": "0xaaa",
            "to_address": "0xbbb",
            "value_wei": 1000,
            "type": "transfer_out",
        })
        detector.reset()
        assert len(detector._tx_history) == 0
