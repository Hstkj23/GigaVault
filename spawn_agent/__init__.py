"""
SpawnAgent — Real-time on-chain intelligence and wallet monitoring platform.

SpawnAgent provides a concurrent, process-per-wallet architecture for monitoring
blockchain addresses, tracing fund flows, and detecting anomalous activity.
"""

__version__ = "0.4.2"
__author__ = "SpawnAgent Contributors"

from spawn_agent.core.agent import SpawnAgent
from spawn_agent.core.supervisor import Supervisor
from spawn_agent.core.process import WorkerProcess

__all__ = [
    "SpawnAgent",
    "Supervisor",
    "WorkerProcess",
    "__version__",
]
