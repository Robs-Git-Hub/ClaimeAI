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
    BATCH_MATCH_HUMAN_PROMPT,
    BATCH_MATCH_SYSTEM_PROMPT,
    BatchMatchOutput,
    MatchProposal,
    VerifyOutput,
    batch_match_claims,
    batch_match_claims_fallback,
    extract_claim_keywords,
    matched_citation_free_indices,
    supersede_stale_no_match,
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

    assert len(result[0].route_verdicts) == 1
    rv = result[0].route_verdicts[0]
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

    assert len(result[0].route_verdicts) == 1
    rv = result[0].route_verdicts[0]
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

    assert len(result[0].route_verdicts) == 1
    rv = result[0].route_verdicts[0]
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
    assert result[0].route_verdicts == []
    assert result[1].route_verdicts == []


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
    assert result[0].route_verdicts == []


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

    assert result[0].route_verdicts == []


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


# ---------------------------------------------------------------------------
# verify_matches — provenance_type (fallback marking)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_matches_default_provenance_type_is_vault_note():
    note = make_vault_note("SOURCE-a", "web-page", body_sections={"": "Supporting content."})
    vault_by_name = {"SOURCE-a": note}
    records = [make_claim_record("Claim one.")]
    proposals = [MatchProposal(claim_index=0, note_name="SOURCE-a", reasoning="Relevant.")]

    mock_response = VerifyOutput(
        verdict="vault_supported", reasoning="Supports it.", supporting_note="SOURCE-a"
    )

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        result = await verify_matches(records, proposals, vault_by_name)

    assert result[0].route_verdicts[0].provenance_type == "vault_note"


@pytest.mark.asyncio
async def test_verify_matches_accepts_fallback_provenance_type():
    note = make_vault_note("SOURCE-a", "web-page", body_sections={"": "Supporting content."})
    vault_by_name = {"SOURCE-a": note}
    records = [make_claim_record("Claim one.")]
    proposals = [MatchProposal(claim_index=0, note_name="SOURCE-a", reasoning="Relevant.")]

    mock_response = VerifyOutput(
        verdict="vault_supported", reasoning="Supports it.", supporting_note="SOURCE-a"
    )

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        result = await verify_matches(
            records, proposals, vault_by_name, provenance_type="vault_note_fallback"
        )

    assert result[0].route_verdicts[0].provenance_type == "vault_note_fallback"


# ---------------------------------------------------------------------------
# batch_match_claims — exclude_indices
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_match_excludes_given_indices():
    records = [
        make_claim_record("Already matched claim."),
        make_claim_record("Still unmatched claim."),
    ]
    vault = make_serialized_vault([make_vault_note("SOURCE-a", "web-page")])

    mock_response = BatchMatchOutput(matches=[])

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ) as mock_llm_call, patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        await batch_match_claims(records, vault, exclude_indices={0})

    _, kwargs = mock_llm_call.call_args
    messages = kwargs["messages"] if "messages" in kwargs else mock_llm_call.call_args[0][2]
    human_prompt = messages[-1][1]
    assert "Already matched claim." not in human_prompt
    assert "Still unmatched claim." in human_prompt


@pytest.mark.asyncio
async def test_batch_match_exclude_indices_none_matches_default_behavior():
    records = [make_claim_record("Claim one.")]
    vault = make_serialized_vault([make_vault_note("SOURCE-a", "web-page")])
    mock_response = BatchMatchOutput(
        matches=[MatchProposal(claim_index=0, note_name="SOURCE-a", reasoning="Relevant.")]
    )

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        result = await batch_match_claims(records, vault)

    assert len(result) == 1


@pytest.mark.asyncio
async def test_batch_match_all_excluded_skips_llm_call():
    records = [make_claim_record("Claim one.")]
    vault = make_serialized_vault([make_vault_note("SOURCE-a", "web-page")])

    with patch(
        "ingest.vault_match.call_llm_with_structured_output", new_callable=AsyncMock
    ) as mock_llm_call:
        result = await batch_match_claims(records, vault, exclude_indices={0})

    mock_llm_call.assert_not_called()
    assert result == []


# ---------------------------------------------------------------------------
# matched_citation_free_indices
# ---------------------------------------------------------------------------


def test_matched_citation_free_indices_confirmed_match():
    records = [
        make_claim_record("Claim one."),
        make_claim_record("Claim two."),
    ]
    records[0].route_verdicts.append(
        RouteVerdict(route="vault_matched", verdict="vault_supported", provenance="SOURCE-a")
    )

    result = matched_citation_free_indices(records)

    assert result == {0}


def test_matched_citation_free_indices_no_vault_match_not_counted():
    records = [make_claim_record("Claim one.")]
    records[0].route_verdicts.append(
        RouteVerdict(route="vault_matched", verdict="no_vault_match", provenance=None)
    )

    result = matched_citation_free_indices(records)

    assert result == set()


def test_matched_citation_free_indices_no_proposal_not_counted():
    records = [make_claim_record("Claim one.")]

    result = matched_citation_free_indices(records)

    assert result == set()


def test_matched_citation_free_indices_ignores_other_routes():
    records = [make_claim_record("Claim one.")]
    records[0].route_verdicts.append(
        RouteVerdict(route="vault_aligned", verdict="vault_supported", provenance="SOURCE-a")
    )

    result = matched_citation_free_indices(records)

    assert result == set()


# ---------------------------------------------------------------------------
# batch_match_claims_fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_sends_all_unmatched_claims_in_one_call():
    records = [
        make_claim_record("Matched already."),
        make_claim_record("Still unmatched one."),
        make_claim_record("Still unmatched two."),
    ]
    full_notes = [make_vault_note("SOURCE-untagged", "web-page", body_sections={"": "Content."})]

    mock_response = BatchMatchOutput(
        matches=[
            MatchProposal(claim_index=1, note_name="SOURCE-untagged", reasoning="Relevant."),
            MatchProposal(claim_index=2, note_name="SOURCE-untagged", reasoning="Also relevant."),
        ]
    )

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ) as mock_llm_call, patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        result = await batch_match_claims_fallback(records, full_notes, already_matched_indices={0})

    # Exactly one LLM call, covering both unmatched claims together.
    mock_llm_call.assert_called_once()
    _, kwargs = mock_llm_call.call_args
    messages = kwargs["messages"] if "messages" in kwargs else mock_llm_call.call_args[0][2]
    human_prompt = messages[-1][1]
    assert "Matched already." not in human_prompt
    assert "Still unmatched one." in human_prompt
    assert "Still unmatched two." in human_prompt
    assert len(result) == 2


@pytest.mark.asyncio
async def test_fallback_logs_corpus_size(caplog):
    records = [make_claim_record("Claim one.")]
    full_notes = [make_vault_note("SOURCE-a", "web-page", body_sections={"": "Content."})]
    mock_response = BatchMatchOutput(matches=[])

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()), caplog.at_level("INFO"):
        await batch_match_claims_fallback(records, full_notes, already_matched_indices=set())

    assert any("Full-vault fallback corpus" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_fallback_logs_warning_when_over_token_budget(caplog):
    records = [make_claim_record("Claim one.")]
    full_notes = [make_vault_note("SOURCE-a", "web-page", body_sections={"": "Content." * 100})]
    mock_response = BatchMatchOutput(matches=[])

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()), patch(
        "ingest.vault_match.FALLBACK_TOKEN_BUDGET", 1
    ), caplog.at_level("WARNING"):
        await batch_match_claims_fallback(records, full_notes, already_matched_indices=set())

    assert any("exceeds budget" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# supersede_stale_no_match
# ---------------------------------------------------------------------------


def test_supersede_removes_stale_no_match_when_finding_exists():
    """Pass 1 rejects a proposal (no_vault_match); the fallback pass later
    finds a real match on the same route. The stale rejection must be
    dropped so the report doesn't show both an absence verdict and a
    finding for the same claim."""
    record = make_claim_record("Claim one.")
    record.route_verdicts = [
        RouteVerdict(
            route="vault_matched",
            verdict="no_vault_match",
            provenance=None,
            provenance_type="vault_note",
        ),
        RouteVerdict(
            route="vault_matched",
            verdict="vault_supported",
            provenance="SOURCE-untagged",
            provenance_type="vault_note_fallback",
        ),
    ]

    result = supersede_stale_no_match([record])

    verdicts = result[0].route_verdicts
    assert len(verdicts) == 1
    assert verdicts[0].verdict == "vault_supported"
    assert verdicts[0].provenance_type == "vault_note_fallback"


def test_supersede_removes_stale_no_match_when_contradicted_finding_exists():
    """Same as above but the superseding finding is a contradiction, not a
    support -- either non-no_vault_match verdict must supersede."""
    record = make_claim_record("Claim one.")
    record.route_verdicts = [
        RouteVerdict(route="vault_matched", verdict="no_vault_match", provenance=None),
        RouteVerdict(
            route="vault_matched",
            verdict="vault_contradicted",
            provenance="SOURCE-untagged",
            provenance_type="vault_note_fallback",
        ),
    ]

    result = supersede_stale_no_match([record])

    verdicts = result[0].route_verdicts
    assert len(verdicts) == 1
    assert verdicts[0].verdict == "vault_contradicted"


def test_supersede_preserves_lone_no_match():
    """No finding ever supersedes the rejection -- it must be preserved
    untouched (this is the common case: the fallback either didn't run, or
    ran and still found nothing)."""
    record = make_claim_record("Claim one.")
    record.route_verdicts = [
        RouteVerdict(route="vault_matched", verdict="no_vault_match", provenance=None),
    ]

    result = supersede_stale_no_match([record])

    assert len(result[0].route_verdicts) == 1
    assert result[0].route_verdicts[0].verdict == "no_vault_match"


def test_supersede_ignores_other_routes():
    """A no_vault_match on vault_matched must not be removed by a finding on
    a different route (e.g. vault_aligned), and verdicts on other routes
    must never be touched or removed."""
    record = make_claim_record("Claim one.")
    record.route_verdicts = [
        RouteVerdict(route="vault_matched", verdict="no_vault_match", provenance=None),
        RouteVerdict(
            route="vault_aligned", verdict="vault_supported", provenance="SOURCE-other"
        ),
    ]

    result = supersede_stale_no_match([record])

    verdicts = result[0].route_verdicts
    assert len(verdicts) == 2
    assert any(rv.route == "vault_matched" and rv.verdict == "no_vault_match" for rv in verdicts)
    assert any(rv.route == "vault_aligned" and rv.verdict == "vault_supported" for rv in verdicts)


def test_supersede_no_records_noop():
    assert supersede_stale_no_match([]) == []


# ---------------------------------------------------------------------------
# batch_match_claims_fallback -- promoted to the "high" tier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_uses_high_tier():
    """Milestone review: the mid-tier model missed a same-subject match with
    a different number ("98 votes" claim vs. a "93 votes" note). The
    fallback is one call per run, so it's promoted to "high"."""
    records = [make_claim_record("Claim one.")]
    full_notes = [make_vault_note("SOURCE-a", "web-page", body_sections={"": "Content."})]
    mock_response = BatchMatchOutput(matches=[])

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()) as mock_get_llm:
        await batch_match_claims_fallback(records, full_notes, already_matched_indices=set())

    mock_get_llm.assert_called_once_with(tier="high")


@pytest.mark.asyncio
async def test_batch_match_claims_default_tier_is_mid():
    """Pass 1 (paper-scoped, filtered corpus) must stay on the cheap tier --
    only the fallback pass is promoted."""
    records = [make_claim_record("Claim one.")]
    vault = make_serialized_vault([make_vault_note("SOURCE-a", "web-page")])
    mock_response = BatchMatchOutput(matches=[])

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.vault_match.get_llm", return_value=MagicMock()) as mock_get_llm:
        await batch_match_claims(records, vault)

    mock_get_llm.assert_called_once_with(tier="mid")


@pytest.mark.asyncio
async def test_fallback_surfaces_priority_candidates_in_prompt():
    """A number shared between an unmatched claim and a note's content
    should appear as a named priority candidate in the human prompt sent to
    the fallback LLM call -- the free, code-only recall boost."""
    records = [make_claim_record("The resolution passed with 98 votes.")]
    full_notes = [
        make_vault_note(
            "SOURCE-vote-count", "web-page", body_sections={"": "The tally was 98 in favor."}
        ),
        make_vault_note("SOURCE-unrelated", "web-page", body_sections={"": "Nothing relevant."}),
    ]
    mock_response = BatchMatchOutput(matches=[])

    with patch(
        "ingest.vault_match.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ) as mock_llm_call, patch("ingest.vault_match.get_llm", return_value=MagicMock()):
        await batch_match_claims_fallback(records, full_notes, already_matched_indices=set())

    _, kwargs = mock_llm_call.call_args
    messages = kwargs["messages"] if "messages" in kwargs else mock_llm_call.call_args[0][2]
    human_prompt = messages[-1][1]
    assert "Priority candidates" in human_prompt
    assert "SOURCE-vote-count" in human_prompt
    assert "98" in human_prompt


# ---------------------------------------------------------------------------
# Prompt wording -- contradiction guidance (recall fix for "98 vs 93 votes")
# ---------------------------------------------------------------------------


def test_batch_match_system_prompt_instructs_contradiction_matches():
    prompt = BATCH_MATCH_SYSTEM_PROMPT.lower()
    assert "contradict" in prompt
    assert "98 votes" in BATCH_MATCH_SYSTEM_PROMPT
    assert "93 votes" in BATCH_MATCH_SYSTEM_PROMPT


def test_batch_match_human_prompt_instructs_contradiction_matches():
    assert "contradict" in BATCH_MATCH_HUMAN_PROMPT.lower()


# ---------------------------------------------------------------------------
# extract_claim_keywords
# ---------------------------------------------------------------------------


def test_extract_claim_keywords_numbers():
    keywords = extract_claim_keywords("The resolution passed with 98 votes.")
    assert "98" in keywords


def test_extract_claim_keywords_proper_nouns():
    keywords = extract_claim_keywords("Ukraine raised the issue at the UN.")
    assert "Ukraine" in keywords
    assert "UN" in keywords


def test_extract_claim_keywords_codes_with_hyphens_and_slashes():
    keywords = extract_claim_keywords("The vote is recorded under ES-11/7.")
    assert "ES-11/7" in keywords


def test_extract_claim_keywords_excludes_common_leading_words():
    keywords = extract_claim_keywords("The vote passed. This was significant.")
    assert "The" not in keywords
    assert "This" not in keywords


def test_extract_claim_keywords_empty_string():
    assert extract_claim_keywords("") == set()
    assert extract_claim_keywords("   ") == set()


def test_extract_claim_keywords_no_keywords():
    assert extract_claim_keywords("it was here") == set()
