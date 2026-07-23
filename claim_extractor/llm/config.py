"""LLM configuration constants.

Central settings for language model behavior.

Model selection lives in the per-role registry in ``utils/models.py``
(MODEL_REGISTRY); extractor nodes request ``role="extraction"``.
"""

# Temperature settings
DEFAULT_TEMPERATURE = 0.0  # Use for exact, consistent outputs
MULTI_COMPLETION_TEMPERATURE = 0.2  # Use for voting with diverse outputs
