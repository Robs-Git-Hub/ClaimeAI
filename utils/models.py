"""Unified LLM model instances and factory functions.

Provides access to configured language model instances for all modules.

Provider selection is driven by ``pipeline.llm_provider`` in
``config.toml`` (overridable by the ``LLM_PROVIDER`` env var):

- ``openai`` (default) — models are created via ``init_chat_model`` against
  the OpenAI API using ``OPENAI_API_KEY``.
- ``openrouter`` — models are created via ``ChatOpenAI`` against OpenRouter's
  OpenAI-compatible endpoint using ``OPENROUTER_API_KEY``.

Model tier mappings and reasoning effort are configured in ``config.toml``
(sections ``[models.*]`` and ``[reasoning.*]``). Nodes only ever ask for a
tier, never a concrete model name.
"""

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from utils.config import config
from utils.settings import settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Loaded from config.toml [models.*] sections; hardcoded fallback when
# config.toml is missing or has no [models] section.
# Rationale: docs/playbook/model-tier-selection.md
_DEFAULT_MODELS: dict[str, dict[str, str]] = {
    "openai": {
        "low": "openai:gpt-4o-mini",
        "mid": "openai:gpt-4.1-mini",
        "high": "openai:gpt-4.1",
    },
    "openrouter": {
        "low": "google/gemma-4-26b-a4b-it",
        "mid": "anthropic/claude-haiku-4.5",
        "high": "anthropic/claude-sonnet-5",
    },
}

MODEL_REGISTRY: dict[str, dict[str, str]] = config.get("models") or _DEFAULT_MODELS

# Loaded from config.toml [reasoning.*] sections. Missing tiers default
# to no reasoning effort (handled by .get() returning None).
_DEFAULT_REASONING: dict[str, dict[str, str]] = {
    "openrouter": {"high": "medium"},
}

REASONING_CONFIG: dict[str, dict[str, str]] = (
    config.get("reasoning") or _DEFAULT_REASONING
)


def resolve_model(tier: str | None = None, provider: str | None = None) -> str:
    """Resolve a pipeline tier to a provider-specific model name.

    Args:
        tier: Cost/quality tier (see MODEL_REGISTRY). None resolves to "low".
        provider: LLM provider; defaults to ``settings.llm_provider``.

    Returns:
        The model identifier for the given tier and provider.

    Raises:
        ValueError: If the provider or tier is unknown.
    """
    provider = provider or settings.llm_provider
    tier = tier or "low"

    try:
        provider_models = MODEL_REGISTRY[provider]
    except KeyError:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. "
            f"Expected one of {sorted(MODEL_REGISTRY)}"
        ) from None

    try:
        return provider_models[tier]
    except KeyError:
        raise ValueError(
            f"Unknown LLM tier '{tier}'. Expected one of {sorted(provider_models)}"
        ) from None


def _get_openai_llm(model_name: str, temperature: float) -> BaseChatModel:
    """Build a chat model against the OpenAI API (original behavior)."""
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key not found in environment variables")

    return init_chat_model(
        model=model_name,
        api_key=settings.openai_api_key,
        temperature=temperature if model_name.startswith("openai:gpt") else None,
    )


def _get_openrouter_llm(
    model_name: str, temperature: float, reasoning_effort: str | None = None
) -> BaseChatModel:
    """Build a chat model against OpenRouter's OpenAI-compatible endpoint."""
    if not settings.openrouter_api_key:
        raise ValueError(
            "OpenRouter API key not found in environment variables. "
            "Set OPENROUTER_API_KEY (or switch LLM_PROVIDER to 'openai')."
        )

    kwargs = {}
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort

    return ChatOpenAI(
        model=model_name,
        api_key=settings.openrouter_api_key,
        base_url=OPENROUTER_BASE_URL,
        temperature=temperature,
        **kwargs,
    )


def get_llm(
    model_name: str | None = None,
    temperature: float = 0.0,
    completions: int = 1,
    tier: str | None = None,
) -> BaseChatModel:
    """Get LLM with specified configuration.

    Args:
        model_name: Explicit model to use. Bypasses the tier registry. A name
            starting with ``openai:`` always routes to the OpenAI path
            (backward compatible); any other name routes to OpenRouter.
        temperature: Temperature for generation (honored on both providers).
        completions: How many completions we need (affects temperature for
            diversity — the 3-completion voting quality gate relies on this).
        tier: Cost/quality tier ("low", "mid", "high") used to resolve the
            model from MODEL_REGISTRY when ``model_name`` is not given.
            Defaults to "low".

    Returns:
        Configured LLM instance.
    """
    # Use higher temp when doing multiple completions for diversity
    if completions > 1 and temperature == 0.0:
        temperature = 0.2

    if model_name is not None:
        # Explicit model name bypasses tier registry (including REASONING_CONFIG).
        if model_name.startswith("openai:"):
            return _get_openai_llm(model_name, temperature)
        return _get_openrouter_llm(model_name, temperature)

    provider = settings.llm_provider
    resolved = resolve_model(tier=tier, provider=provider)

    if provider == "openrouter":
        reasoning_effort = REASONING_CONFIG.get(provider, {}).get(tier or "low")
        return _get_openrouter_llm(resolved, temperature, reasoning_effort)
    return _get_openai_llm(resolved, temperature)


def get_default_llm() -> BaseChatModel:
    """Get default LLM instance."""
    return get_llm()
