"""Node configuration settings.

Contains settings for the claim verification pipeline nodes.
Search settings are loaded from config.toml [pipeline] section.
"""

from utils.config import config

_pipeline = config.get("pipeline", {})

# Node settings
QUERY_GENERATION_CONFIG = {
    "temperature": 0.0,
}

EVIDENCE_RETRIEVAL_CONFIG = {
    "results_per_query": _pipeline.get("results_per_query", 3),
    "search_provider": _pipeline.get("search_provider", "exa"),
}

EVIDENCE_EVALUATION_CONFIG = {
    "temperature": 0.0,
}

ITERATIVE_SEARCH_CONFIG = {
    "max_iterations": _pipeline.get("max_search_iterations", 5),
}
