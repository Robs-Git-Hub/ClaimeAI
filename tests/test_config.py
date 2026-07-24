"""Tests for TOML configuration loading.

Verifies that config.toml is loaded correctly, missing files fall back
to empty dict, and malformed TOML raises a clear error.
"""

import tomllib
from pathlib import Path

import pytest

from utils.config import _load_config


@pytest.fixture
def config_file(tmp_path):
    """Write a temporary config.toml and return its path."""

    def _write(content: str) -> Path:
        path = tmp_path / "config.toml"
        path.write_text(content, encoding="utf-8")
        return path

    return _write


def test_missing_file_returns_empty_dict(tmp_path):
    assert _load_config(tmp_path / "nonexistent.toml") == {}


def test_reads_pipeline_section(config_file):
    path = config_file(
        '[pipeline]\nllm_provider = "openrouter"\nsearch_provider = "tavily"\n'
    )
    result = _load_config(path)
    assert result["pipeline"]["llm_provider"] == "openrouter"
    assert result["pipeline"]["search_provider"] == "tavily"


def test_reads_models_section(config_file):
    path = config_file(
        '[models.openai]\nlow = "openai:gpt-4o-mini"\n'
        '[models.openrouter]\nlow = "google/gemma-4-26b-a4b-it"\n'
    )
    result = _load_config(path)
    assert result["models"]["openai"]["low"] == "openai:gpt-4o-mini"
    assert result["models"]["openrouter"]["low"] == "google/gemma-4-26b-a4b-it"


def test_reads_reasoning_section(config_file):
    path = config_file('[reasoning.openrouter]\nhigh = "medium"\n')
    result = _load_config(path)
    assert result["reasoning"]["openrouter"]["high"] == "medium"
    assert result["reasoning"]["openrouter"].get("low") is None


def test_reads_search_settings(config_file):
    path = config_file(
        "[pipeline]\nresults_per_query = 5\nmax_search_iterations = 3\n"
    )
    result = _load_config(path)
    assert result["pipeline"]["results_per_query"] == 5
    assert result["pipeline"]["max_search_iterations"] == 3


def test_reads_summarize_evidence_flag_override(config_file):
    """TG 03.4: summarize_evidence is config-switchable (default true,
    see test_real_config_toml_loads / claim_verifier/config/nodes.py)."""
    path = config_file("[pipeline]\nsummarize_evidence = false\n")
    result = _load_config(path)
    assert result["pipeline"]["summarize_evidence"] is False


def test_malformed_toml_raises(config_file):
    path = config_file("this is not [[[valid toml")
    with pytest.raises(tomllib.TOMLDecodeError):
        _load_config(path)


def test_real_config_toml_loads():
    """The project's actual config.toml must load without error."""
    repo_root = Path(__file__).resolve().parent.parent
    config_path = repo_root / "config.toml"
    if config_path.exists():
        result = _load_config(config_path)
        assert "pipeline" in result
        assert "models" in result
        # TG 03.4: summarize_evidence defaults to true in the real config.
        assert result["pipeline"].get("summarize_evidence", True) is True
