"""Tests for the batch triage classifier (TG 03.1).

``triage_claims`` classifies every claim in a draft in one cheap (``mid``
tier) LLM call, populating ``triage_class``, ``citation_expectation``, and
``importance`` on each ``ClaimRecord``. Conservative-up: any claim the LLM
omits, or that the LLM call as a whole fails to produce, is left
unclassified (``None`` fields) rather than defaulted to "trivial" — TG 03.2
routing treats unclassified claims as needing verification.

See ingest/triage.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claim_verifier.schemas import Verdict, VerificationResult
from ingest.triage import (
    TRIAGE_SYSTEM_PROMPT,
    BatchTriageOutput,
    TriageProposal,
    triage_claims,
)
from utils.claim_record import CitationStatus, ClaimRecord, DraftPosition


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_triage_populates_fields():
    records = [
        make_claim_record("The sky is blue."),
        make_claim_record("Our model achieves 94% accuracy on the test set."),
    ]

    mock_response = BatchTriageOutput(
        classifications=[
            TriageProposal(
                claim_index=0,
                triage_class="trivial",
                citation_expectation="not-expected",
                importance=1,
                reasoning="Common knowledge.",
            ),
            TriageProposal(
                claim_index=1,
                triage_class="novel-result",
                citation_expectation="not-expected",
                importance=5,
                reasoning="Author's own experimental result.",
            ),
        ]
    )

    with patch(
        "ingest.triage.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.triage.get_llm", return_value=MagicMock()):
        result = await triage_claims(records)

    assert result[0].triage_class == "trivial"
    assert result[0].citation_expectation == "not-expected"
    assert result[0].importance == 1

    assert result[1].triage_class == "novel-result"
    assert result[1].citation_expectation == "not-expected"
    assert result[1].importance == 5


@pytest.mark.asyncio
async def test_triage_uses_mid_tier():
    records = [make_claim_record("Claim.")]
    mock_response = BatchTriageOutput(classifications=[])

    with patch(
        "ingest.triage.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.triage.get_llm", return_value=MagicMock()) as mock_get_llm:
        await triage_claims(records)

    mock_get_llm.assert_called_once_with(tier="mid")


@pytest.mark.asyncio
async def test_triage_includes_cited_and_citation_free_claims():
    """Unlike vault_match's batch_match_claims, triage runs over every claim
    regardless of citation status — routing (TG 03.2) needs triage on cited
    claims too."""
    records = [
        make_claim_record("Cited claim text.", citation_status=CitationStatus.CITED),
        make_claim_record("Citation-free claim text.", citation_status=CitationStatus.CITATION_FREE),
    ]
    mock_response = BatchTriageOutput(classifications=[])

    with patch(
        "ingest.triage.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ) as mock_llm_call, patch("ingest.triage.get_llm", return_value=MagicMock()):
        await triage_claims(records)

    _, kwargs = mock_llm_call.call_args
    messages = kwargs["messages"]
    human_prompt = messages[-1][1]
    assert "Cited claim text." in human_prompt
    assert "Citation-free claim text." in human_prompt


# ---------------------------------------------------------------------------
# Empty input / no-op paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_triage_empty_input_early_exit():
    with patch(
        "ingest.triage.call_llm_with_structured_output", new_callable=AsyncMock
    ) as mock_llm_call:
        result = await triage_claims([])

    mock_llm_call.assert_not_called()
    assert result == []


@pytest.mark.asyncio
async def test_triage_skips_claims_without_web_verdict():
    records = [
        ClaimRecord(
            web_verdict=None,
            citation_status=CitationStatus.CITATION_FREE,
            cite_set=[],
            position=DraftPosition(sentence_index=0),
        )
    ]

    with patch(
        "ingest.triage.call_llm_with_structured_output", new_callable=AsyncMock
    ) as mock_llm_call:
        result = await triage_claims(records)

    mock_llm_call.assert_not_called()
    assert result[0].triage_class is None
    assert result[0].citation_expectation is None
    assert result[0].importance is None


# ---------------------------------------------------------------------------
# Failure / conservative-degrade paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_triage_llm_failure_leaves_fields_none():
    records = [make_claim_record("Claim one."), make_claim_record("Claim two.")]

    with patch(
        "ingest.triage.call_llm_with_structured_output",
        new=AsyncMock(return_value=None),
    ), patch("ingest.triage.get_llm", return_value=MagicMock()):
        result = await triage_claims(records)

    for record in result:
        assert record.triage_class is None
        assert record.citation_expectation is None
        assert record.importance is None


@pytest.mark.asyncio
async def test_triage_out_of_range_index_ignored():
    records = [make_claim_record("Claim one.")]
    mock_response = BatchTriageOutput(
        classifications=[
            TriageProposal(
                claim_index=99,
                triage_class="trivial",
                citation_expectation="not-expected",
                importance=1,
            )
        ]
    )

    with patch(
        "ingest.triage.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.triage.get_llm", return_value=MagicMock()):
        result = await triage_claims(records)

    assert result[0].triage_class is None
    assert result[0].citation_expectation is None
    assert result[0].importance is None


@pytest.mark.asyncio
async def test_triage_omitted_claim_stays_unclassified_not_trivial():
    """A claim the LLM has no opinion on (omitted from the response) must
    stay None — never defaulted to 'trivial'. Downstream routing treats
    None as 'needs verification'."""
    records = [
        make_claim_record("Claim the LLM will classify."),
        make_claim_record("Claim the LLM stays silent on."),
    ]
    mock_response = BatchTriageOutput(
        classifications=[
            TriageProposal(
                claim_index=0,
                triage_class="general-factual",
                citation_expectation="expected",
                importance=3,
            )
        ]
    )

    with patch(
        "ingest.triage.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.triage.get_llm", return_value=MagicMock()):
        result = await triage_claims(records)

    assert result[0].triage_class == "general-factual"

    assert result[1].triage_class is None
    assert result[1].citation_expectation is None
    assert result[1].importance is None


# ---------------------------------------------------------------------------
# Importance validation / clamping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_triage_importance_clamped_above_range():
    records = [make_claim_record("Claim.")]
    mock_response = BatchTriageOutput(
        classifications=[
            TriageProposal(
                claim_index=0,
                triage_class="academic-citable",
                citation_expectation="expected",
                importance=7,
            )
        ]
    )

    with patch(
        "ingest.triage.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.triage.get_llm", return_value=MagicMock()):
        result = await triage_claims(records)

    assert result[0].importance == 5


@pytest.mark.asyncio
async def test_triage_importance_clamped_below_range():
    records = [make_claim_record("Claim.")]
    mock_response = BatchTriageOutput(
        classifications=[
            TriageProposal(
                claim_index=0,
                triage_class="dataset-dependent",
                citation_expectation="optional",
                importance=0,
            )
        ]
    )

    with patch(
        "ingest.triage.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.triage.get_llm", return_value=MagicMock()):
        result = await triage_claims(records)

    assert result[0].importance == 1


# ---------------------------------------------------------------------------
# Does not touch vault-derived fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_triage_does_not_overwrite_vault_derived_fields():
    record = make_claim_record("Claim one.")
    record.claim_strength = 4
    record.evidence_quality = 5
    records = [record]

    mock_response = BatchTriageOutput(
        classifications=[
            TriageProposal(
                claim_index=0,
                triage_class="trivial",
                citation_expectation="not-expected",
                importance=1,
            )
        ]
    )

    with patch(
        "ingest.triage.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.triage.get_llm", return_value=MagicMock()):
        result = await triage_claims(records)

    assert result[0].claim_strength == 4
    assert result[0].evidence_quality == 5


# ---------------------------------------------------------------------------
# Prompt-content assertions (Phase 03 milestone review fix)
# ---------------------------------------------------------------------------


def test_prompt_excludes_public_record_facts_from_dataset_dependent():
    """Motivating failure: the classifier labeled a UN General Assembly vote
    tally -- an official public record -- as dataset-dependent, which routed
    it away from web verification and let a real error ("98 votes", actually
    93) go undetected. The prompt must explicitly carve out public-record
    facts (vote tallies, published statistics, government/IGO records) from
    dataset-dependent and novel-result."""
    prompt = TRIAGE_SYSTEM_PROMPT.lower()

    assert "public record" in prompt
    assert "vote" in prompt
    assert "government" in prompt or "igo" in prompt


def test_prompt_has_directional_tie_break_toward_web_verifiable():
    """When uncertain between a never-web class (dataset-dependent,
    novel-result) and a web-verifiable class (general-factual,
    academic-citable), the prompt must instruct choosing the web-verifiable
    class -- this complements the existing "never choose trivial when
    uncertain" rule; both push toward more verification, since a missed
    error is the worst-case outcome."""
    prompt = TRIAGE_SYSTEM_PROMPT.lower()

    assert "never-web" in prompt
    assert "web-verifiable" in prompt
    assert "missed error" in prompt or "worst-case" in prompt
