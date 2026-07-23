"""Fact Checker - Orchestration system for fact-checking pipelines.

Integrates claim extraction and verification into a complete workflow.
"""

from fact_checker.agent import create_graph, graph
from fact_checker.schemas import FactCheckReport, State

__all__ = [
    # Main functionality
    "create_graph",
    "graph",
    # Data models
    "State",
    "FactCheckReport",
]
