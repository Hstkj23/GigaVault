"""Analysis modules for on-chain data processing."""

from spawn_agent.analysis.graph import WalletGraph
from spawn_agent.analysis.anomaly import AnomalyDetector
from spawn_agent.analysis.patterns import PatternMatcher

__all__ = ["WalletGraph", "AnomalyDetector", "PatternMatcher"]
