"""Node configuration settings.

Contains settings for the claim verification pipeline nodes.
"""

# Node settings
QUERY_GENERATION_CONFIG = {
    "temperature": 0.0,  # Zero temp for consistent results
}

EVIDENCE_RETRIEVAL_CONFIG = {
    "results_per_query": 3,  # Number of search results to fetch per query
    "search_provider": "exa",  # Search provider: "exa" or "tavily"
}

EVIDENCE_EVALUATION_CONFIG = {
    "temperature": 0.0,  # Zero temp for consistent results
}

ITERATIVE_SEARCH_CONFIG = {
    "max_iterations": 5,
}
