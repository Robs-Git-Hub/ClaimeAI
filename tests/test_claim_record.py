"""Tests for the multi-attribute claim record (TG 02.1.2).

ClaimRecord is the data contract for Phases 02-05. It wraps the existing
Phase 01 `Verdict` model (from claim_verifier.schemas) rather than
duplicating its fields. See docs/playbook/claim-record-design.md.
"""

import pytest
from pydantic import ValidationError

from claim_verifier.schemas import Evidence, Verdict, VerificationResult
from utils.claim_record import (
    CitationStatus,
    ClaimRecord,
    DraftPosition,
    RouteVerdict,
    SuggestedAction,
    VaultVerdict,
)


# ---------------------------------------------------------------------------
# Enum values
# ---------------------------------------------------------------------------


def test_citation_status_values():
    assert {member.value for member in CitationStatus} == {
        "cited",
        "citation_free",
        "unparsed_citation",
    }


def test_vault_verdict_values():
    assert {member.value for member in VaultVerdict} == {
        "vault_supported",
        "vault_contradicted",
        "not_supported",
        "note_not_in_vault",
        "insufficient_vault_content",
        "no_vault_match",
    }


def test_suggested_action_values():
    assert {member.value for member in SuggestedAction} == {
        "none",
        "fix_citation",
        "add_citation",
        "add_vault_note",
        "revise_claim",
        "unresolved",
    }


# ---------------------------------------------------------------------------
# DraftPosition
# ---------------------------------------------------------------------------


def test_draft_position_requires_sentence_index_only():
    position = DraftPosition(sentence_index=3)
    assert position.sentence_index == 3
    assert position.section is None
    assert position.section_index is None
    assert position.char_start is None
    assert position.char_end is None


def test_draft_position_missing_sentence_index_raises():
    with pytest.raises(ValidationError):
        DraftPosition()


def test_draft_position_all_fields():
    position = DraftPosition(
        sentence_index=7,
        section="Introduction",
        section_index=0,
        char_start=120,
        char_end=180,
    )
    assert position.sentence_index == 7
    assert position.section == "Introduction"
    assert position.section_index == 0
    assert position.char_start == 120
    assert position.char_end == 180


# ---------------------------------------------------------------------------
# RouteVerdict
# ---------------------------------------------------------------------------


def test_route_verdict_required_fields_only():
    rv = RouteVerdict(route="web", verdict="Supported")
    assert rv.route == "web"
    assert rv.verdict == "Supported"
    assert rv.reasoning is None
    assert rv.provenance is None
    assert rv.provenance_type is None


def test_route_verdict_all_fields():
    rv = RouteVerdict(
        route="vault_aligned",
        verdict=VaultVerdict.VAULT_SUPPORTED.value,
        reasoning="Matched a QUOTE note directly.",
        provenance="Some Vault Note",
        provenance_type="vault_note",
    )
    assert rv.route == "vault_aligned"
    assert rv.verdict == "vault_supported"
    assert rv.reasoning == "Matched a QUOTE note directly."
    assert rv.provenance == "Some Vault Note"
    assert rv.provenance_type == "vault_note"


def test_route_verdict_missing_required_raises():
    with pytest.raises(ValidationError):
        RouteVerdict(route="web")


# ---------------------------------------------------------------------------
# ClaimRecord construction
# ---------------------------------------------------------------------------


def test_claim_record_minimal():
    record = ClaimRecord(
        web_verdict=None,
        citation_status=CitationStatus.CITATION_FREE,
        cite_set=[],
        position=DraftPosition(sentence_index=0),
    )
    assert record.web_verdict is None
    assert record.citation_status == CitationStatus.CITATION_FREE
    assert record.cite_set == []
    assert record.position.sentence_index == 0
    assert record.route_verdicts == []
    assert record.suggested_action is None
    assert record.claim_strength is None
    assert record.evidence_quality is None
    assert record.triage_class is None
    assert record.citation_expectation is None
    assert record.importance is None


def test_claim_record_full():
    verdict = Verdict(
        claim_text="The sky is blue.",
        disambiguated_sentence="The sky is blue.",
        original_sentence="The sky is blue.",
        original_index=0,
        result=VerificationResult.SUPPORTED,
        reasoning="Well established fact.",
        sources=[
            Evidence(url="https://example.com", text="The sky appears blue.", title="Sky facts")
        ],
    )
    route_verdict = RouteVerdict(
        route="vault_matched",
        verdict=VaultVerdict.NO_VAULT_MATCH.value,
        reasoning="No matching vault note found.",
        provenance=None,
        provenance_type=None,
    )
    record = ClaimRecord(
        web_verdict=verdict,
        citation_status=CitationStatus.CITED,
        cite_set=["Some Source Note"],
        position=DraftPosition(
            sentence_index=4,
            section="Background",
            section_index=1,
            char_start=200,
            char_end=260,
        ),
        route_verdicts=[route_verdict],
        suggested_action=SuggestedAction.NONE,
        claim_strength=4,
        evidence_quality=5,
        triage_class="major",
        citation_expectation="expected",
        importance=3,
    )
    assert record.web_verdict is verdict
    assert record.citation_status == CitationStatus.CITED
    assert record.cite_set == ["Some Source Note"]
    assert record.position.section == "Background"
    assert record.route_verdicts == [route_verdict]
    assert record.suggested_action == SuggestedAction.NONE
    assert record.claim_strength == 4
    assert record.evidence_quality == 5
    assert record.triage_class == "major"
    assert record.citation_expectation == "expected"
    assert record.importance == 3


def test_claim_record_requires_citation_status():
    with pytest.raises(ValidationError):
        ClaimRecord(position=DraftPosition(sentence_index=0))


# ---------------------------------------------------------------------------
# Phase 03 placeholders default to None
# ---------------------------------------------------------------------------


def test_phase_03_placeholders_default_to_none():
    record = ClaimRecord(
        citation_status=CitationStatus.CITATION_FREE,
        position=DraftPosition(sentence_index=0),
    )
    assert record.triage_class is None
    assert record.citation_expectation is None
    assert record.importance is None


# ---------------------------------------------------------------------------
# Vault metadata fields
# ---------------------------------------------------------------------------


def test_vault_metadata_defaults_to_none():
    record = ClaimRecord(
        citation_status=CitationStatus.CITATION_FREE,
        position=DraftPosition(sentence_index=0),
    )
    assert record.claim_strength is None
    assert record.evidence_quality is None


@pytest.mark.parametrize("value", [1, 2, 3, 4, 5])
def test_vault_metadata_accepts_int_1_to_5(value):
    record = ClaimRecord(
        citation_status=CitationStatus.CITATION_FREE,
        position=DraftPosition(sentence_index=0),
        claim_strength=value,
        evidence_quality=value,
    )
    assert record.claim_strength == value
    assert record.evidence_quality == value


# ---------------------------------------------------------------------------
# Defaults: cite_set and position not passed
# ---------------------------------------------------------------------------


def test_cite_set_defaults_to_empty_list():
    record = ClaimRecord(citation_status=CitationStatus.CITATION_FREE)
    assert record.cite_set == []


def test_position_defaults_to_none():
    record = ClaimRecord(citation_status=CitationStatus.CITATION_FREE)
    assert record.position is None


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


def test_serialization_round_trip():
    verdict = Verdict(
        claim_text="Water boils at 100C at sea level.",
        disambiguated_sentence="Water boils at 100C at sea level.",
        original_sentence="Water boils at 100C at sea level.",
        original_index=2,
        result=VerificationResult.SUPPORTED,
        reasoning="Standard physical fact.",
        sources=[Evidence(url="https://example.com/boil", text="Boiling point info")],
    )
    original = ClaimRecord(
        web_verdict=verdict,
        citation_status=CitationStatus.UNPARSED_CITATION,
        cite_set=["Note A", "Note B"],
        position=DraftPosition(sentence_index=2, section="Methods", section_index=2),
        route_verdicts=[
            RouteVerdict(route="vault_aligned", verdict="not_supported", reasoning="Quote mismatch")
        ],
        suggested_action=SuggestedAction.FIX_CITATION,
        claim_strength=3,
        evidence_quality=2,
        triage_class="minor",
        citation_expectation="not_expected",
        importance=1,
    )

    dumped = original.model_dump()
    restored = ClaimRecord.model_validate(dumped)

    assert restored == original
    assert restored.model_dump() == dumped


# ---------------------------------------------------------------------------
# ClaimRecord with existing Verdict
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 03 (TG 03.2): routing_decision / routing_reason
# ---------------------------------------------------------------------------


def test_routing_fields_default_to_none():
    record = ClaimRecord(
        citation_status=CitationStatus.CITATION_FREE,
        position=DraftPosition(sentence_index=0),
    )
    assert record.routing_decision is None
    assert record.routing_reason is None


def test_routing_fields_settable():
    record = ClaimRecord(
        citation_status=CitationStatus.CITATION_FREE,
        position=DraftPosition(sentence_index=0),
        routing_decision="route-web",
        routing_reason="general: routed to 'web'",
    )
    assert record.routing_decision == "route-web"
    assert record.routing_reason == "general: routed to 'web'"


def test_routing_fields_serialization_round_trip():
    original = ClaimRecord(
        citation_status=CitationStatus.CITATION_FREE,
        position=DraftPosition(sentence_index=0),
        routing_decision="skip-trivial",
        routing_reason="trivial: no verification needed.",
    )
    dumped = original.model_dump()
    restored = ClaimRecord.model_validate(dumped)
    assert restored == original
    assert restored.routing_decision == "skip-trivial"
    assert restored.routing_reason == "trivial: no verification needed."


def test_claim_record_wraps_existing_verdict():
    verdict = Verdict(
        claim_text="The Earth orbits the Sun.",
        disambiguated_sentence="The Earth orbits the Sun.",
        original_sentence="The Earth orbits the Sun.",
        original_index=0,
        result=VerificationResult.SUPPORTED,
        reasoning="Basic astronomy.",
        sources=[],
    )
    record = ClaimRecord(
        web_verdict=verdict,
        citation_status=CitationStatus.CITATION_FREE,
    )
    assert record.web_verdict.claim_text == "The Earth orbits the Sun."
    assert record.web_verdict.result == VerificationResult.SUPPORTED
