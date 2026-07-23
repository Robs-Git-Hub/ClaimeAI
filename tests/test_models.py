"""Tests for provider-aware LLM factory (TG 01.3 - OpenRouter integration).

No network calls are made: constructing a LangChain chat-model client only
builds a local object. Tests inspect the returned client's configuration.
"""

import pytest

import utils.models as models
from utils.models import MODEL_REGISTRY, OPENROUTER_BASE_URL, get_llm, resolve_model


@pytest.fixture
def openai_settings(monkeypatch):
    """Settings configured for the default OpenAI provider."""
    monkeypatch.setattr(models.settings, "llm_provider", "openai")
    monkeypatch.setattr(models.settings, "openai_api_key", "sk-proj-test")
    monkeypatch.setattr(models.settings, "openrouter_api_key", None)


@pytest.fixture
def openrouter_settings(monkeypatch):
    """Settings configured for the OpenRouter provider."""
    monkeypatch.setattr(models.settings, "llm_provider", "openrouter")
    monkeypatch.setattr(models.settings, "openai_api_key", None)
    monkeypatch.setattr(models.settings, "openrouter_api_key", "sk-or-v1-test")


# ---------------------------------------------------------------------------
# Registry / tier resolution
# ---------------------------------------------------------------------------


def test_registry_covers_all_tiers_for_both_providers():
    tiers = {"low", "mid", "high"}
    assert set(MODEL_REGISTRY.keys()) == {"openai", "openrouter"}
    for provider_models in MODEL_REGISTRY.values():
        assert set(provider_models.keys()) == tiers


def test_resolve_model_openai_tiers():
    assert resolve_model(tier="low", provider="openai") == "openai:gpt-4o-mini"
    assert resolve_model(tier="mid", provider="openai") == "openai:gpt-4.1-mini"
    assert resolve_model(tier="high", provider="openai") == "openai:gpt-4.1"
    assert resolve_model(provider="openai") == "openai:gpt-4o-mini"


def test_resolve_model_openrouter_tiers():
    assert (
        resolve_model(tier="low", provider="openrouter")
        == "google/gemma-4-26b-a4b-it"
    )
    assert (
        resolve_model(tier="mid", provider="openrouter")
        == "anthropic/claude-haiku-4.5"
    )
    assert (
        resolve_model(tier="high", provider="openrouter")
        == "anthropic/claude-sonnet-5"
    )
    assert resolve_model(provider="openrouter") == "google/gemma-4-26b-a4b-it"


def test_resolve_model_rejects_unknown_tier():
    with pytest.raises(ValueError):
        resolve_model(tier="nonexistent_tier", provider="openai")


def test_evidence_evaluation_quality_gate():
    # Quality gate: high tier must be the smartest model per provider.
    assert MODEL_REGISTRY["openai"]["high"] == "openai:gpt-4.1"
    assert MODEL_REGISTRY["openrouter"]["high"] == "anthropic/claude-sonnet-5"


# ---------------------------------------------------------------------------
# OpenAI path (default provider — behavior unchanged)
# ---------------------------------------------------------------------------


def test_openai_default_model_unchanged(openai_settings):
    llm = get_llm()
    assert llm.model_name == "gpt-4o-mini"
    assert llm.temperature == 0.0


def test_openai_tier_resolution(openai_settings):
    llm = get_llm(tier="high")
    assert llm.model_name == "gpt-4.1"


def test_openai_explicit_model_name_backward_compat(openai_settings):
    llm = get_llm(model_name="openai:gpt-4.1")
    assert llm.model_name == "gpt-4.1"


def test_openai_temperature_honored(openai_settings):
    llm = get_llm(temperature=0.5)
    assert llm.temperature == 0.5


def test_openai_voting_temperature(openai_settings):
    # Voting nodes rely on multi-completion diversity temperature.
    llm = get_llm(completions=3)
    assert llm.temperature == 0.2


def test_openai_missing_key_raises(openai_settings, monkeypatch):
    monkeypatch.setattr(models.settings, "openai_api_key", None)
    with pytest.raises(ValueError):
        get_llm()


def test_openai_client_does_not_use_openrouter_base_url(openai_settings):
    llm = get_llm()
    assert getattr(llm, "openai_api_base", None) != OPENROUTER_BASE_URL


# ---------------------------------------------------------------------------
# OpenRouter path
# ---------------------------------------------------------------------------


def test_openrouter_client_base_url_and_key(openrouter_settings):
    llm = get_llm(tier="low")
    assert llm.openai_api_base == OPENROUTER_BASE_URL
    assert llm.openai_api_key.get_secret_value() == "sk-or-v1-test"
    assert llm.model_name == "google/gemma-4-26b-a4b-it"


def test_openrouter_tier_resolution(openrouter_settings):
    assert get_llm(tier="mid").model_name == "anthropic/claude-haiku-4.5"
    assert get_llm(tier="high").model_name == "anthropic/claude-sonnet-5"


def test_openrouter_default_tier(openrouter_settings):
    llm = get_llm()
    assert llm.model_name == "google/gemma-4-26b-a4b-it"


def test_openrouter_temperature_honored(openrouter_settings):
    llm = get_llm(tier="low", temperature=0.7)
    assert llm.temperature == 0.7


def test_openrouter_voting_temperature(openrouter_settings):
    # The voting quality gate (3 completions, temp 0.2) must work on OpenRouter.
    llm = get_llm(tier="low", completions=3)
    assert llm.temperature == 0.2


def test_openrouter_missing_key_raises(openrouter_settings, monkeypatch):
    monkeypatch.setattr(models.settings, "openrouter_api_key", None)
    with pytest.raises(ValueError, match="[Oo]pen[Rr]outer"):
        get_llm(tier="low")


def test_explicit_openai_model_routes_to_openai_even_under_openrouter(
    openrouter_settings, monkeypatch
):
    # Backward compat: an explicit "openai:" model string always uses the
    # OpenAI path (and therefore requires the OpenAI key).
    monkeypatch.setattr(models.settings, "openai_api_key", "sk-proj-test")
    llm = get_llm(model_name="openai:gpt-4.1")
    assert llm.model_name == "gpt-4.1"
    assert getattr(llm, "openai_api_base", None) != OPENROUTER_BASE_URL
