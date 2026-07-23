"""Tests for LLM provider settings (TG 01.3 - OpenRouter integration).

All tests construct Settings directly with ``_env_file=None`` and explicit
values so they are independent of any real ``.env`` file or ambient
environment variables.
"""

import pytest
from pydantic import ValidationError

from utils.settings import Settings

# Env vars that could leak into Settings from the host environment.
_SETTINGS_ENV_VARS = [
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "LLM_PROVIDER",
    "EXA_API_KEY",
    "TAVILY_API_KEY",
    "REDIS_URL",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Isolate tests from the host environment."""
    for var in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _make_settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


# ---------------------------------------------------------------------------
# LLM_PROVIDER
# ---------------------------------------------------------------------------


def test_llm_provider_defaults_to_openai():
    settings = _make_settings()
    assert settings.llm_provider == "openai"


def test_llm_provider_accepts_openrouter():
    settings = _make_settings(LLM_PROVIDER="openrouter")
    assert settings.llm_provider == "openrouter"


def test_llm_provider_accepts_openai_explicitly():
    settings = _make_settings(LLM_PROVIDER="openai")
    assert settings.llm_provider == "openai"


def test_llm_provider_is_normalized_case_insensitively():
    settings = _make_settings(LLM_PROVIDER="OpenRouter")
    assert settings.llm_provider == "openrouter"


def test_llm_provider_rejects_junk():
    with pytest.raises(ValidationError):
        _make_settings(LLM_PROVIDER="anthropic-direct")


def test_llm_provider_read_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    settings = _make_settings()
    assert settings.llm_provider == "openrouter"


# ---------------------------------------------------------------------------
# OPENROUTER_API_KEY
# ---------------------------------------------------------------------------


def test_openrouter_api_key_is_optional():
    settings = _make_settings()
    assert settings.openrouter_api_key is None


def test_openrouter_api_key_accepts_sk_or_prefix():
    settings = _make_settings(OPENROUTER_API_KEY="sk-or-v1-abc123")
    assert settings.openrouter_api_key == "sk-or-v1-abc123"


def test_openrouter_api_key_rejects_wrong_prefix():
    with pytest.raises(ValidationError):
        _make_settings(OPENROUTER_API_KEY="sk-proj-not-an-openrouter-key")


def test_openrouter_api_key_read_from_environment(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-from-env")
    settings = _make_settings()
    assert settings.openrouter_api_key == "sk-or-v1-from-env"


# ---------------------------------------------------------------------------
# Existing validators must remain intact
# ---------------------------------------------------------------------------


def test_openai_api_key_still_requires_sk_proj_prefix():
    with pytest.raises(ValidationError):
        _make_settings(OPENAI_API_KEY="sk-plain-key")


def test_openai_api_key_accepts_sk_proj_prefix():
    settings = _make_settings(OPENAI_API_KEY="sk-proj-abc123")
    assert settings.openai_api_key == "sk-proj-abc123"


def test_openai_api_key_still_optional():
    settings = _make_settings()
    assert settings.openai_api_key is None
