"""LLM configuration constants.

Central settings for language model behavior.

Model selection lives in the per-tier registry in ``utils/models.py``
(MODEL_REGISTRY); verifier nodes request ``tier="mid"`` (query generation,
search decision) or ``tier="high"`` (evidence evaluation).
"""

# Temperature settings
DEFAULT_TEMPERATURE = 0.0  # Use for exact, consistent outputs (no randomness)
