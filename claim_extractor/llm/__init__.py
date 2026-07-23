"""LLM utilities for claim extraction.

Access to language models and related configuration.
"""

from claim_extractor.llm.config import (
    DEFAULT_TEMPERATURE,
    MULTI_COMPLETION_TEMPERATURE,
)

__all__ = [
    # Config
    "DEFAULT_TEMPERATURE",
    "MULTI_COMPLETION_TEMPERATURE",
]
