"""Tests for citation-free vault matching (TG 02.5).

``batch_match_claims`` proposes candidate claim<->note matches in one cheap
(``mid`` tier) LLM call across all citation-free claims. ``verify_matches``
independently verifies each proposal at the ``high`` tier and appends
``RouteVerdict`` entries (route="vault_matched") to the matched
``ClaimRecord``.

See ingest/vault_match.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claim_verifier.schemas import Verdict, VerificationResult
from ingest.alignment import GatherResult
from ingest.vault_match import (
    BatchMatchOutput,
    MatchProposal,
    VerifyOutput,
    batch_match_claims,
    verify_matches,
)
from ingest.vault_serializer import SerializedVault, VaultNote
from utils.claim_record import (
    CitationStatus,
    ClaimRecord,
    DraftPosition,
    RouteVerdict,
    VaultVerdict,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def make_vault_note(name, note_type, body_sections=None, wikilinks=None, frontmatter=None):
    fm = frontmatter or {"type": note_type}
    return VaultNote(
        name=name,
        note_type=note_type,
        frontmatter=fm,
        body_sections=body_sections or {},
        wikilinks=wikilinks or [],
        file_path=f"v-research/{name}.md",
    )


def make_verdict(claim_text, original_index=0):
    return Verdict(
        claim_text=claim_text,
        disambiguated_sentence=claim_text,
        original_sentence=claim_text,
        original_index=original_index,
        result=VerificationResult.SUPPORTED,
        reasoning="Test.",
        sources=[],
    )


def make_claim_record(claim_text, citation_status=CitationStatus.CITATION_FREE):
    return ClaimRecord(
        web_verdict=make_verdict(claim_text) if claim_text else None,
        citation_status=citation_status,
        cite_set=[],
        position=DraftPosition(sentence_index=0),
    )


def make_serialized_vault(notes):
    serialized = [
        {
            "name": n.name,
            "type": n.note_type,
            "frontmatter": n.frontmatter,
            "sections": n.body_sections,
            "wikilinks": n.wikilinks,
        }
        for n in notes
    ]
    return SerializedVault(
        notes=serialized,
        note_count=len(notes),
        token_estimate=100,
        warnings=[],
        argument_pyramid=None,
    )


# ---------------------------------------------------------------------------
# batch_match_claims
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_match_returns_proposals():
    records = [
        make_claim_record("Claim one."),
        make_claim_record("Claim two."),
    ]
    vault = make_serialized_vault([make_vault_note("SOURCE-a", "web-page")])

    mock_response = BatchMatchOutput(
        matches=[
            MatchProposal(claim_index=0, note_name="SOURCE-a", reasoning="Relevant."),
            MatchProposal(claim_index=1, note_name="SOURCE-a", reasoning="Also relevant."),
        ]
    )

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        result = await batch_match_claims(records, vault)

    assert len(result) == 2
    assert all(isinstance(p, MatchProposal) for p in result)
    assert result[0].claim_index == 0
    assert result[1].claim_index == 1


@pytest.mark.asyncio
async def test_batch_match_skips_cited_claims():
    records = [
        make_claim_record("Cited claim.", citation_status=CitationStatus.CITED),
        make_claim_record("Citation-free claim.", citation_status=CitationStatus.CITATION_FREE),
    ]
    vault = make_serialized_vault([make_vault_note("SOURCE-a", "web-page")])

    mock_response = BatchMatchOutput(matches=[])

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ) as mock_llm_call, patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        await batch_match_claims(records, vault)

    # Inspect the human prompt sent to the LLM
    _, kwargs = mock_llm_call.call_args
    messages = kwargs["messages"] if "messages" in kwargs else mock_llm_call.call_args[0][2]
    human_prompt = messages[-1][1]
    assert "Cited claim." not in human_prompt
    assert "Citation-free claim." in human_prompt


@pytest.mark.asyncio
async def test_batch_match_empty_claims():
    records = [make_claim_record("Cited.", citation_status=CitationStatus.CITED)]
    vault = make_serialized_vault([])

    with patch(
        "ingest.vault_match.call_llm_with_structured_output", new_callable=AsyncMock
    ) as mock_llm_call:
        result = await batch_match_claims(records, vault)

    mock_llm_call.assert_not_called()
    assert result == []


@pytest.mark.asyncio
async def test_batch_match_llm_returns_none():
    records = [make_claim_record("Claim.")]
    vault = make_serialized_vault([make_vault_note("SOURCE-a", "web-page")])

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=None),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        result = await batch_match_claims(records, vault)

    assert result == []


@pytest.mark.asyncio
async def test_batch_match_skips_no_web_verdict():
    records = [
        ClaimRecord(
            web_verdict=None,
            citation_status=CitationStatus.CITATION_FREE,
            cite_set=[],
            position=DraftPosition(sentence_index=0),
        )
    ]
    vault = make_serialized_vault([make_vault_note("SOURCE-a", "web-page")])

    with patch(
        "ingest.vault_match.call_llm_with_structured_output", new_callable=AsyncMock
    ) as mock_llm_call:
        result = await batch_match_claims(records, vault)

    mock_llm_call.assert_not_called()
    assert result == []


# ---------------------------------------------------------------------------
# verify_matches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_supported_match():
    note = make_vault_note("SOURCE-a", "web-page", body_sections={"": "Supporting content."})
    vault_by_name = {"SOURCE-a": note}
    records = [make_claim_record("Claim one.")]
    proposals = [MatchProposal(claim_index=0, note_name="SOURCE-a", reasoning="Relevant.")]

    mock_response = VerifyOutput(
        verdict="vault_supported",
        reasoning="Directly supports the claim.",
        supporting_note="SOURCE-a",
    )

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        result = await verify_matches(records, proposals, vault_by_name)

    assert len(result[0].vault_verdicts) == 1
    rv = result[0].vault_verdicts[0]
    assert isinstance(rv, RouteVerdict)
    assert rv.route == "vault_matched"
    assert rv.verdict == "vault_supported"
    assert rv.reasoning == "Directly supports the claim."
    assert rv.provenance == "SOURCE-a"
    assert rv.provenance_type == "vault_note"


@pytest.mark.asyncio
async def test_verify_no_vault_match():
    note = make_vault_note("SOURCE-a", "web-page", body_sections={"": "Unrelated content."})
    vault_by_name = {"SOURCE-a": note}
    records = [make_claim_record("Claim one.")]
    proposals = [MatchProposal(claim_index=0, note_name="SOURCE-a", reasoning="Maybe relevant.")]

    mock_response = VerifyOutput(
        verdict="no_vault_match",
        reasoning="Does not address the claim.",
        supporting_note=None,
    )

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        result = await verify_matches(records, proposals, vault_by_name)

    assert len(result[0].vault_verdicts) == 1
    rv = result[0].vault_verdicts[0]
    assert rv.verdict == "no_vault_match"
    assert rv.route == "vault_matched"


@pytest.mark.asyncio
async def test_verify_contradicted_match():
    note = make_vault_note("SOURCE-a", "web-page", body_sections={"": "Contradicting content."})
    vault_by_name = {"SOURCE-a": note}
    records = [make_claim_record("Claim one.")]
    proposals = [MatchProposal(claim_index=0, note_name="SOURCE-a", reasoning="Maybe relevant.")]

    mock_response = VerifyOutput(
        verdict="vault_contradicted",
        reasoning="Directly contradicts the claim.",
        supporting_note="SOURCE-a",
    )

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        result = await verify_matches(records, proposals, vault_by_name)

    assert len(result[0].vault_verdicts) == 1
    rv = result[0].vault_verdicts[0]
    assert rv.verdict == "vault_contradicted"
    assert rv.route == "vault_matched"


@pytest.mark.asyncio
async def test_verify_out_of_range_index_skipped():
    note = make_vault_note("SOURCE-a", "web-page", body_sections={"": "Content."})
    vault_by_name = {"SOURCE-a": note}
    records = [make_claim_record("Claim one."), make_claim_record("Claim two.")]
    proposals = [MatchProposal(claim_index=99, note_name="SOURCE-a", reasoning="Out of range.")]

    with patch(
        "ingest.vault_match.call_llm_with_structured_output", new_callable=AsyncMock
    ) as mock_llm_call:
        result = await verify_matches(records, proposals, vault_by_name)

    mock_llm_call.assert_not_called()
    assert result[0].vault_verdicts == []
    assert result[1].vault_verdicts == []


@pytest.mark.asyncio
async def test_verify_note_not_in_vault_skipped():
    vault_by_name = {}
    records = [make_claim_record("Claim one.")]
    proposals = [MatchProposal(claim_index=0, note_name="SOURCE-missing", reasoning="Guessed.")]

    with patch(
        "ingest.vault_match.call_llm_with_structured_output", new_callable=AsyncMock
    ) as mock_llm_call:
        result = await verify_matches(records, proposals, vault_by_name)

    mock_llm_call.assert_not_called()
    assert result[0].vault_verdicts == []


@pytest.mark.asyncio
async def test_verify_llm_returns_none_skipped():
    note = make_vault_note("SOURCE-a", "web-page", body_sections={"": "Content."})
    vault_by_name = {"SOURCE-a": note}
    records = [make_claim_record("Claim one.")]
    proposals = [MatchProposal(claim_index=0, note_name="SOURCE-a", reasoning="Relevant.")]

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=None),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        result = await verify_matches(records, proposals, vault_by_name)

    assert result[0].vault_verdicts == []


@pytest.mark.asyncio
async def test_verify_copies_claim_strength_from_claim_note():
    note = make_vault_note(
        "CLAIM-a",
        "claim",
        body_sections={"": "Claim note content."},
        frontmatter={"type": "claim", "claim_strength": 4, "evidence_quality": 3},
    )
    vault_by_name = {"CLAIM-a": note}
    records = [make_claim_record("Claim one.")]
    proposals = [MatchProposal(claim_index=0, note_name="CLAIM-a", reasoning="Relevant.")]

    mock_response = VerifyOutput(
        verdict="vault_supported",
        reasoning="Supports it.",
        supporting_note="CLAIM-a",
    )

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        result = await verify_matches(records, proposals, vault_by_name)

    assert result[0].claim_strength == 4
    assert result[0].evidence_quality == 3


@pytest.mark.asyncio
async def test_verify_no_copy_if_not_claim_type():
    note = make_vault_note(
        "SOURCE-a",
        "web-page",
        body_sections={"": "Source content."},
        frontmatter={"type": "web-page", "claim_strength": 5, "evidence_quality": 5},
    )
    vault_by_name = {"SOURCE-a": note}
    records = [make_claim_record("Claim one.")]
    proposals = [MatchProposal(claim_index=0, note_name="SOURCE-a", reasoning="Relevant.")]

    mock_response = VerifyOutput(
        verdict="vault_supported",
        reasoning="Supports it.",
        supporting_note="SOURCE-a",
    )

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        result = await verify_matches(records, proposals, vault_by_name)

    assert result[0].claim_strength is None
    assert result[0].evidence_quality is None


@pytest.mark.asyncio
async def test_verify_no_copy_if_not_supported():
    note = make_vault_note(
        "CLAIM-a",
        "claim",
        body_sections={"": "Claim note content."},
        frontmatter={"type": "claim", "claim_strength": 4, "evidence_quality": 3},
    )
    vault_by_name = {"CLAIM-a": note}
    records = [make_claim_record("Claim one.")]
    proposals = [MatchProposal(claim_index=0, note_name="CLAIM-a", reasoning="Maybe relevant.")]

    mock_response = VerifyOutput(
        verdict="no_vault_match",
        reasoning="Does not support it.",
        supporting_note=None,
    )

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        result = await verify_matches(records, proposals, vault_by_name)

    assert result[0].claim_strength is None
    assert result[0].evidence_quality is None
