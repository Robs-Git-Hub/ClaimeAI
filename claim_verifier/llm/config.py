"""LLM configuration constants.

Central settings for language model behavior.

Model selection lives in the per-role registry in ``utils/models.py``
(MODEL_REGISTRY); verifier nodes request ``role="query_generation"``,
``role="search_decision"``, or ``role="evidence_evaluation"``.
"""

# Temperature settings
DEFAULT_TEMPERATURE = 0.0  # Use for exact, consistent outputs (no randomness)
