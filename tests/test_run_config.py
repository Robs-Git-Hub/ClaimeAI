"""Tests for run configuration models (TG 02.1.3).

Covers ``RunProfile`` (light/heavy) and ``ResourceManifest`` (declares what
evidence sources exist for a run). See docs/playbook/claim-record-design.md
for the design contract.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from utils.run_config import ResourceManifest, RunProfile


# ---------------------------------------------------------------------------
# RunProfile
# ---------------------------------------------------------------------------


def test_run_profile_has_exactly_two_values():
    assert set(RunProfile) == {RunProfile.LIGHT, RunProfile.HEAVY}
    assert len(RunProfile) == 2


def test_run_profile_values_are_strings():
    assert RunProfile.LIGHT.value == "light"
    assert RunProfile.HEAVY.value == "heavy"


def test_run_profile_constructible_from_string():
    assert RunProfile("light") is RunProfile.LIGHT
    assert RunProfile("heavy") is RunProfile.HEAVY


# ---------------------------------------------------------------------------
# ResourceManifest -- valid construction
# ---------------------------------------------------------------------------


def test_minimal_manifest_draft_path_only():
    manifest = ResourceManifest(draft_path="draft.md")
    assert manifest.draft_path == Path("draft.md")
    assert manifest.vault_path is None
    assert manifest.argument_pyramid is None
    assert manifest.corpus_ids is None
    assert manifest.web_enabled is True


def test_full_manifest_all_fields_set():
    manifest = ResourceManifest(
        draft_path="draft.md",
        vault_path="vault/",
        argument_pyramid="pyramid-a",
        corpus_ids=["doc-1", "doc-2"],
        web_enabled=False,
    )
    assert manifest.draft_path == Path("draft.md")
    assert manifest.vault_path == Path("vault/")
    assert manifest.argument_pyramid == "pyramid-a"
    assert manifest.corpus_ids == ["doc-1", "doc-2"]
    assert manifest.web_enabled is False


def test_default_web_enabled_is_true():
    manifest = ResourceManifest(draft_path="draft.md")
    assert manifest.web_enabled is True


def test_draft_path_accepts_str_and_path():
    manifest_str = ResourceManifest(draft_path="draft.md")
    manifest_path = ResourceManifest(draft_path=Path("draft.md"))
    assert manifest_str.draft_path == manifest_path.draft_path == Path("draft.md")


# ---------------------------------------------------------------------------
# ResourceManifest -- vault-less degradation
# ---------------------------------------------------------------------------


def test_manifest_without_vault_path_validates():
    manifest = ResourceManifest(draft_path="draft.md")
    assert manifest.vault_path is None


def test_has_vault_false_when_vault_path_none():
    manifest = ResourceManifest(draft_path="draft.md")
    assert manifest.has_vault is False


def test_has_vault_true_when_vault_path_set():
    manifest = ResourceManifest(draft_path="draft.md", vault_path="vault/")
    assert manifest.has_vault is True


# ---------------------------------------------------------------------------
# ResourceManifest -- validation
# ---------------------------------------------------------------------------


def test_manifest_without_draft_path_raises():
    with pytest.raises(ValidationError):
        ResourceManifest()


def test_corpus_ids_defaults_to_none():
    manifest = ResourceManifest(draft_path="draft.md")
    assert manifest.corpus_ids is None


def test_argument_pyramid_defaults_to_none():
    manifest = ResourceManifest(draft_path="draft.md")
    assert manifest.argument_pyramid is None


# ---------------------------------------------------------------------------
# ResourceManifest -- helper methods
# ---------------------------------------------------------------------------


def test_available_routes_web_only_no_vault():
    manifest = ResourceManifest(draft_path="draft.md")
    assert manifest.available_routes == ["web"]


def test_available_routes_web_and_vault():
    manifest = ResourceManifest(draft_path="draft.md", vault_path="vault/")
    assert manifest.available_routes == ["web", "vault_aligned", "vault_matched"]


def test_available_routes_vault_only_web_disabled():
    manifest = ResourceManifest(
        draft_path="draft.md", vault_path="vault/", web_enabled=False
    )
    assert manifest.available_routes == ["vault_aligned", "vault_matched"]


def test_available_routes_empty_when_nothing_available():
    manifest = ResourceManifest(draft_path="draft.md", web_enabled=False)
    assert manifest.available_routes == []


def test_manifest_serialization_round_trip():
    manifest = ResourceManifest(
        draft_path="draft.md",
        vault_path="vault/",
        argument_pyramid="pyramid-a",
        corpus_ids=["doc-1"],
        web_enabled=False,
    )
    dumped = manifest.model_dump()
    restored = ResourceManifest.model_validate(dumped)
    assert restored == manifest


# ---------------------------------------------------------------------------
# Profile + Manifest interaction
# ---------------------------------------------------------------------------


def test_light_profile_with_vault_present_manifest_is_valid():
    profile = RunProfile.LIGHT
    manifest = ResourceManifest(draft_path="draft.md", vault_path="vault/")
    assert profile is RunProfile.LIGHT
    assert manifest.has_vault is True


def test_heavy_profile_with_vault_less_manifest_is_valid():
    profile = RunProfile.HEAVY
    manifest = ResourceManifest(draft_path="draft.md")
    assert profile is RunProfile.HEAVY
    assert manifest.has_vault is False
    assert manifest.available_routes == ["web"]
