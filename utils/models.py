"""Unified LLM model instances and factory functions.

Provides access to configured language model instances for all modules.

Provider selection is driven by ``LLM_PROVIDER`` (see ``utils/settings.py``):

- ``openai`` (default) — models are created via ``init_chat_model`` against
  the OpenAI API using ``OPENAI_API_KEY``.
- ``openrouter`` — models are created via ``ChatOpenAI`` against OpenRouter's
  OpenAI-compatible endpoint using ``OPENROUTER_API_KEY``.

Each pipeline role maps to a model tier per provider via ``MODEL_REGISTRY``.
"""

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from utils.settings import settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Per-role model registry (single source of truth for model selection).
#
# Roles:
#   extraction          — claim extractor nodes (selection, disambiguation,
#                         decomposition, validation); high-volume, cheap tier.
#   query_generation    — search query generation for verification.
#   search_decision     — decide whether another search iteration is needed.
#   evidence_evaluation — final verdict on a claim. QUALITY GATE: this role
#                         must NEVER map below Opus-tier (OpenRouter) /
#                         GPT-4.1-tier (OpenAI). Do not downgrade this call.
#   default             — fallback when no role is given.
#
# OpenRouter model IDs verified against openrouter.ai on 2026-07-22
# (current tiers: claude-haiku-4.5 / claude-sonnet-5 / claude-opus-4.8).
# Re-confirm IDs at live-test time (task 01.3.5) before first paid run.
MODEL_REGISTRY: dict[str, dict[str, str]] = {
    "openai": {
        "default": "openai:gpt-4o-mini",
        "extraction": "openai:gpt-4o-mini",
        "query_generation": "openai:gpt-4.1-mini",
        "search_decision": "openai:gpt-4.1-mini",
        "evidence_evaluation": "openai:gpt-4.1",
    },
    "openrouter": {
        "default": "anthropic/claude-haiku-4.5",
        "extraction": "anthropic/claude-haiku-4.5",
        "query_generation": "anthropic/claude-sonnet-5",
        "search_decision": "anthropic/claude-sonnet-5",
        # Never below Opus-tier — evidence evaluation is the primary
        # quality mechanism of the verifier.
        "evidence_evaluation": "anthropic/claude-opus-4.8",
    },
}


def resolve_model(role: str | None = None, provider: str | None = None) -> str:
    """Resolve a pipeline role to a provider-specific model name.

    Args:
        role: Pipeline role (see MODEL_REGISTRY). None resolves to "default".
        provider: LLM provider; defaults to ``settings.llm_provider``.

    Returns:
        The model identifier for the given role and provider.

    Raises:
        ValueError: If the provider or role is unknown.
    """
    provider = provider or settings.llm_provider
    role = role or "default"

    try:
        provider_models = MODEL_REGISTRY[provider]
    except KeyError:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. "
            f"Expected one of {sorted(MODEL_REGISTRY)}"
        ) from None

    try:
        return provider_models[role]
    except KeyError:
        raise ValueError(
            f"Unknown LLM role '{role}'. Expected one of {sorted(provider_models)}"
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


def _get_openrouter_llm(model_name: str, temperature: float) -> BaseChatModel:
    """Build a chat model against OpenRouter's OpenAI-compatible endpoint."""
    if not settings.openrouter_api_key:
        raise ValueError(
            "OpenRouter API key not found in environment variables. "
            "Set OPENROUTER_API_KEY (or switch LLM_PROVIDER to 'openai')."
        )

    return ChatOpenAI(
        model=model_name,
        api_key=settings.openrouter_api_key,
        base_url=OPENROUTER_BASE_URL,
        temperature=temperature,
    )


def get_llm(
    model_name: str | None = None,
    temperature: float = 0.0,
    completions: int = 1,
    role: str | None = None,
) -> BaseChatModel:
    """Get LLM with specified configuration.

    Args:
        model_name: Explicit model to use. Bypasses the role registry. A name
            starting with ``openai:`` always routes to the OpenAI path
            (backward compatible); any other name routes to OpenRouter.
        temperature: Temperature for generation (honored on both providers).
        completions: How many completions we need (affects temperature for
            diversity — the 3-completion voting quality gate relies on this).
        role: Pipeline role used to resolve the model from MODEL_REGISTRY
            when ``model_name`` is not given.

    Returns:
        Configured LLM instance.
    """
    # Use higher temp when doing multiple completions for diversity
    if completions > 1 and temperature == 0.0:
        temperature = 0.2

    if model_name is not None:
        # Explicit model name: route by its format for backward compatibility.
        if model_name.startswith("openai:"):
            return _get_openai_llm(model_name, temperature)
        return _get_openrouter_llm(model_name, temperature)

    provider = settings.llm_provider
    resolved = resolve_model(role=role, provider=provider)

    if provider == "openrouter":
        return _get_openrouter_llm(resolved, temperature)
    return _get_openai_llm(resolved, temperature)


def get_default_llm() -> BaseChatModel:
    """Get default LLM instance."""
    return get_llm()
