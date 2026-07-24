"""Tests for cited-claim alignment (TG 02.4).

``gather_evidence`` is a pure, synchronous evidence-gathering function (no
LLM calls) that walks a cited vault note plus its one-hop wikilinks.
``evaluate_alignment`` is the async LangGraph-node-shaped function that
calls the LLM (at ``high`` tier) to decide whether the gathered evidence
supports, contradicts, or fails to support a claim.

See ingest/alignment.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claim_verifier.schemas import Verdict, VerificationResult
from ingest.alignment import (
    AlignmentOutput,
    GatherResult,
    evaluate_alignment,
    gather_evidence,
)
from ingest.vault_serializer import VaultNote
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


def make_vault_note(name, note_type, body_sections=None, wikilinks=None):
    return VaultNote(
        name=name,
        note_type=note_type,
        frontmatter={"type": note_type},
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


def make_claim_record(claim_text, cite_set, citation_status=CitationStatus.CITED):
    return ClaimRecord(
        web_verdict=make_verdict(claim_text) if claim_text is not None else None,
        citation_status=citation_status,
        cite_set=cite_set,
        position=DraftPosition(sentence_index=0),
    )


# ---------------------------------------------------------------------------
# gather_evidence
# ---------------------------------------------------------------------------


def test_gather_note_not_in_vault():
    result = gather_evidence("SOURCE-missing", {})

    assert isinstance(result, GatherResult)
    assert result.cited_note_name is None
    assert result.verdict == VaultVerdict.NOTE_NOT_IN_VAULT.value


def test_gather_source_with_quote_child():
    quote = make_vault_note(
        "QUOTE-a", "quotation", body_sections={"": "The quoted text."}
    )
    source = make_vault_note(
        "SOURCE-a",
        "web-page",
        body_sections={"": "About the source."},
        wikilinks=["QUOTE-a"],
    )
    vault_by_name = {"SOURCE-a": source, "QUOTE-a": quote}

    result = gather_evidence("SOURCE-a", vault_by_name)

    assert result.cited_note_name is not None
    assert result.cited_note_name == "SOURCE-a"
    assert result.cited_note_type == "web-page"
    assert result.cited_note_content == "About the source."
    assert len(result.linked_notes) == 1
    assert result.linked_notes[0].name == "QUOTE-a"
    assert result.linked_notes[0].note_type == "quotation"
    assert result.linked_notes[0].content == "The quoted text."


def test_gather_result_note_with_linked_hyp():
    hyp = make_vault_note("HYP-1", "hypothesis", body_sections={"": "The hypothesis."})
    result_note = make_vault_note(
        "RESULT-1",
        "result",
        body_sections={"": "The result content."},
        wikilinks=["HYP-1"],
    )
    vault_by_name = {"RESULT-1": result_note, "HYP-1": hyp}

    result = gather_evidence("RESULT-1", vault_by_name)

    assert result.cited_note_name is not None
    assert result.cited_note_content == "The result content."
    assert len(result.linked_notes) == 1
    assert result.linked_notes[0].name == "HYP-1"
    assert result.linked_notes[0].content == "The hypothesis."


def test_gather_note_no_body_no_links():
    empty_note = make_vault_note("SOURCE-empty", "web-page")
    vault_by_name = {"SOURCE-empty": empty_note}

    result = gather_evidence("SOURCE-empty", vault_by_name)

    assert result.cited_note_name is None
    assert result.verdict == VaultVerdict.INSUFFICIENT_VAULT_CONTENT.value


def test_gather_note_with_body_no_links():
    note = make_vault_note(
        "SOURCE-solo", "web-page", body_sections={"": "Solo content."}
    )
    vault_by_name = {"SOURCE-solo": note}

    result = gather_evidence("SOURCE-solo", vault_by_name)

    assert result.cited_note_name is not None
    assert result.cited_note_content == "Solo content."
    assert result.linked_notes == []


def test_gather_linked_note_not_in_vault_skipped():
    quote = make_vault_note("QUOTE-a", "quotation", body_sections={"": "Real quote."})
    source = make_vault_note(
        "SOURCE-a",
        "web-page",
        body_sections={"": "Source content."},
        wikilinks=["QUOTE-a", "QUOTE-missing"],
    )
    vault_by_name = {"SOURCE-a": source, "QUOTE-a": quote}

    result = gather_evidence("SOURCE-a", vault_by_name)

    assert result.cited_note_name is not None
    assert len(result.linked_notes) == 1
    assert result.linked_notes[0].name == "QUOTE-a"


def test_gather_one_hop_only():
    note_c = make_vault_note("NOTE-c", "claim", body_sections={"": "C content."})
    note_b = make_vault_note(
        "NOTE-b",
        "quotation",
        body_sections={"": "B content."},
        wikilinks=["NOTE-c"],
    )
    note_a = make_vault_note(
        "NOTE-a",
        "web-page",
        body_sections={"": "A content."},
        wikilinks=["NOTE-b"],
    )
    vault_by_name = {"NOTE-a": note_a, "NOTE-b": note_b, "NOTE-c": note_c}

    result = gather_evidence("NOTE-a", vault_by_name)

    assert result.cited_note_name is not None
    assert result.cited_note_name == "NOTE-a"
    assert len(result.linked_notes) == 1
    assert result.linked_notes[0].name == "NOTE-b"
    linked_names = {ln.name for ln in result.linked_notes}
    assert "NOTE-c" not in linked_names


def test_gather_multiple_linked_notes():
    linked_1 = make_vault_note("LINK-1", "quotation", body_sections={"": "One."})
    linked_2 = make_vault_note("LINK-2", "observation", body_sections={"": "Two."})
    linked_3 = make_vault_note("LINK-3", "paraphrase", body_sections={"": "Three."})
    source = make_vault_note(
        "SOURCE-multi",
        "web-page",
        body_sections={"": "Main."},
        wikilinks=["LINK-1", "LINK-2", "LINK-3"],
    )
    vault_by_name = {
        "SOURCE-multi": source,
        "LINK-1": linked_1,
        "LINK-2": linked_2,
        "LINK-3": linked_3,
    }

    result = gather_evidence("SOURCE-multi", vault_by_name)

    assert result.cited_note_name is not None
    assert len(result.linked_notes) == 3
    names = {ln.name for ln in result.linked_notes}
    assert names == {"LINK-1", "LINK-2", "LINK-3"}


# ---------------------------------------------------------------------------
# evaluate_alignment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_skips_citation_free():
    record = make_claim_record(
        "Some claim.", cite_set=[], citation_status=CitationStatus.CITATION_FREE
    )

    with patch(
        "ingest.alignment.call_llm_with_structured_output", new_callable=AsyncMock
    ) as mock_llm_call:
        result = await evaluate_alignment(record, {})

    mock_llm_call.assert_not_called()
    assert result is record
    assert result.vault_verdicts == []


@pytest.mark.asyncio
async def test_evaluate_skips_empty_cite_set():
    record = make_claim_record(
        "Some claim.", cite_set=[], citation_status=CitationStatus.CITED
    )

    with patch(
        "ingest.alignment.call_llm_with_structured_output", new_callable=AsyncMock
    ) as mock_llm_call:
        result = await evaluate_alignment(record, {})

    mock_llm_call.assert_not_called()
    assert result is record
    assert result.vault_verdicts == []


@pytest.mark.asyncio
async def test_evaluate_supported_verdict():
    source = make_vault_note(
        "SOURCE-a", "web-page", body_sections={"": "Supporting content."}
    )
    vault_by_name = {"SOURCE-a": source}
    record = make_claim_record("The sky is blue.", cite_set=["SOURCE-a"])

    mock_response = AlignmentOutput(
        verdict="vault_supported",
        reasoning="Directly supports the claim.",
        supporting_note="SOURCE-a",
    )

    with patch(
        "ingest.alignment.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.alignment.get_llm", return_value=MagicMock()):
        result = await evaluate_alignment(record, vault_by_name)

    assert len(result.vault_verdicts) == 1
    rv = result.vault_verdicts[0]
    assert isinstance(rv, RouteVerdict)
    assert rv.route == "vault_aligned"
    assert rv.verdict == "vault_supported"
    assert rv.reasoning == "Directly supports the claim."
    assert rv.provenance == "SOURCE-a"
    assert rv.provenance_type == "vault_note"


@pytest.mark.asyncio
async def test_evaluate_not_supported_verdict():
    source = make_vault_note(
        "SOURCE-b", "web-page", body_sections={"": "Unrelated content."}
    )
    vault_by_name = {"SOURCE-b": source}
    record = make_claim_record("A miscited claim.", cite_set=["SOURCE-b"])

    mock_response = AlignmentOutput(
        verdict="not_supported",
        reasoning="The note does not address this claim.",
        supporting_note=None,
    )

    with patch(
        "ingest.alignment.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.alignment.get_llm", return_value=MagicMock()):
        result = await evaluate_alignment(record, vault_by_name)

    assert len(result.vault_verdicts) == 1
    rv = result.vault_verdicts[0]
    assert rv.verdict == "not_supported"
    # Falls back to the note name when the LLM gives no supporting_note.
    assert rv.provenance == "SOURCE-b"
    assert rv.provenance_type == "vault_note"


@pytest.mark.asyncio
async def test_evaluate_contradicted_verdict():
    source = make_vault_note(
        "SOURCE-c", "web-page", body_sections={"": "Contradicting content."}
    )
    vault_by_name = {"SOURCE-c": source}
    record = make_claim_record("A contradicted claim.", cite_set=["SOURCE-c"])

    mock_response = AlignmentOutput(
        verdict="vault_contradicted",
        reasoning="The evidence directly contradicts the claim.",
        supporting_note="SOURCE-c",
    )

    with patch(
        "ingest.alignment.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.alignment.get_llm", return_value=MagicMock()):
        result = await evaluate_alignment(record, vault_by_name)

    assert len(result.vault_verdicts) == 1
    rv = result.vault_verdicts[0]
    assert rv.route == "vault_aligned"
    assert rv.verdict == "vault_contradicted"
    assert rv.reasoning == "The evidence directly contradicts the claim."
    assert rv.provenance == "SOURCE-c"
    assert rv.provenance_type == "vault_note"


@pytest.mark.asyncio
async def test_evaluate_skips_empty_claim_text():
    source = make_vault_note(
        "SOURCE-a", "web-page", body_sections={"": "Content."}
    )
    vault_by_name = {"SOURCE-a": source}
    verdict = Verdict(
        claim_text="",
        disambiguated_sentence="",
        original_sentence="",
        original_index=0,
        result=VerificationResult.SUPPORTED,
        reasoning="Test.",
        sources=[],
    )
    record = ClaimRecord(
        web_verdict=verdict,
        citation_status=CitationStatus.CITED,
        cite_set=["SOURCE-a"],
        position=DraftPosition(sentence_index=0),
    )

    with patch(
        "ingest.alignment.call_llm_with_structured_output", new_callable=AsyncMock
    ) as mock_llm_call:
        result = await evaluate_alignment(record, vault_by_name)

    mock_llm_call.assert_not_called()
    assert result.vault_verdicts == []


@pytest.mark.asyncio
async def test_evaluate_note_not_in_vault():
    record = make_claim_record("A claim.", cite_set=["SOURCE-missing"])

    with patch(
        "ingest.alignment.call_llm_with_structured_output", new_callable=AsyncMock
    ) as mock_llm_call:
        result = await evaluate_alignment(record, {})

    mock_llm_call.assert_not_called()
    assert len(result.vault_verdicts) == 1
    rv = result.vault_verdicts[0]
    assert rv.route == "vault_aligned"
    assert rv.verdict == VaultVerdict.NOTE_NOT_IN_VAULT.value
    assert rv.provenance == "SOURCE-missing"
    assert rv.provenance_type is None


@pytest.mark.asyncio
async def test_evaluate_insufficient_content():
    empty_note = make_vault_note("SOURCE-empty", "web-page")
    vault_by_name = {"SOURCE-empty": empty_note}
    record = make_claim_record("A claim.", cite_set=["SOURCE-empty"])

    with patch(
        "ingest.alignment.call_llm_with_structured_output", new_callable=AsyncMock
    ) as mock_llm_call:
        result = await evaluate_alignment(record, vault_by_name)

    mock_llm_call.assert_not_called()
    assert len(result.vault_verdicts) == 1
    rv = result.vault_verdicts[0]
    assert rv.verdict == VaultVerdict.INSUFFICIENT_VAULT_CONTENT.value
    assert rv.provenance == "SOURCE-empty"


@pytest.mark.asyncio
async def test_evaluate_union_semantics():
    supported_note = make_vault_note(
        "SOURCE-good", "web-page", body_sections={"": "Good content."}
    )
    unrelated_note = make_vault_note(
        "SOURCE-bad", "web-page", body_sections={"": "Unrelated content."}
    )
    vault_by_name = {"SOURCE-good": supported_note, "SOURCE-bad": unrelated_note}
    record = make_claim_record(
        "A dual-cited claim.", cite_set=["SOURCE-good", "SOURCE-bad"]
    )

    responses = [
        AlignmentOutput(
            verdict="vault_supported", reasoning="Supports it.", supporting_note="SOURCE-good"
        ),
        AlignmentOutput(
            verdict="not_supported", reasoning="Doesn't address it.", supporting_note=None
        ),
    ]

    with patch(
        "ingest.alignment.call_llm_with_structured_output",
        new=AsyncMock(side_effect=responses),
    ), patch("ingest.alignment.get_llm", return_value=MagicMock()):
        result = await evaluate_alignment(record, vault_by_name)

    assert len(result.vault_verdicts) == 2
    verdicts = {rv.provenance: rv.verdict for rv in result.vault_verdicts}
    assert verdicts["SOURCE-good"] == "vault_supported"
    assert verdicts["SOURCE-bad"] == "not_supported"


@pytest.mark.asyncio
async def test_evaluate_llm_returns_none():
    source = make_vault_note(
        "SOURCE-a", "web-page", body_sections={"": "Some content."}
    )
    vault_by_name = {"SOURCE-a": source}
    record = make_claim_record("A claim.", cite_set=["SOURCE-a"])

    with patch(
        "ingest.alignment.call_llm_with_structured_output",
        new=AsyncMock(return_value=None),
    ), patch("ingest.alignment.get_llm", return_value=MagicMock()):
        result = await evaluate_alignment(record, vault_by_name)

    assert result.vault_verdicts == []


@pytest.mark.asyncio
async def test_evaluate_no_web_verdict():
    record = ClaimRecord(
        web_verdict=None,
        citation_status=CitationStatus.CITED,
        cite_set=["SOURCE-a"],
        position=DraftPosition(sentence_index=0),
    )

    with patch(
        "ingest.alignment.call_llm_with_structured_output", new_callable=AsyncMock
    ) as mock_llm_call:
        result = await evaluate_alignment(record, {"SOURCE-a": make_vault_note("SOURCE-a", "web-page")})

    mock_llm_call.assert_not_called()
    assert result.vault_verdicts == []


@pytest.mark.asyncio
async def test_evaluate_provenance_recorded():
    source = make_vault_note(
        "SOURCE-prov", "web-page", body_sections={"": "Some content."}
    )
    linked = make_vault_note(
        "QUOTE-prov", "quotation", body_sections={"": "A strong quote."}
    )
    source.wikilinks = ["QUOTE-prov"]
    vault_by_name = {"SOURCE-prov": source, "QUOTE-prov": linked}
    record = make_claim_record("A claim.", cite_set=["SOURCE-prov"])

    mock_response = AlignmentOutput(
        verdict="vault_supported",
        reasoning="The linked quote supports it.",
        supporting_note="QUOTE-prov",
    )

    with patch(
        "ingest.alignment.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("ingest.alignment.get_llm", return_value=MagicMock()):
        result = await evaluate_alignment(record, vault_by_name)

    rv = result.vault_verdicts[0]
    assert rv.provenance == "QUOTE-prov"
    assert rv.provenance_type == "vault_note"
