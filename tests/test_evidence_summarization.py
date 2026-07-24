"""Tests for evidence summarization (TG 03.4).

``summarize_evidence_for_claim`` (claim_verifier/evidence_summarization.py)
is the reusable core: one LLM call (mid tier) condenses a claim's raw
evidence set into claim-relevant extracts, tied back to their original
source by 1-based index so URL/title attribution never depends on the
model's output. It is a pre-processing step called from within
``evaluate_evidence_node`` (claim_verifier/nodes/evaluate_evidence.py),
not a separate graph node — see the module docstring in
evidence_summarization.py for why (the ``evidence`` state field uses an
``add`` reducer, so a node returning a condensed evidence update would
concatenate onto the raw accumulated evidence rather than replace it).

All LLM calls are mocked — no live calls, no network.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import claim_verifier.evidence_summarization as evidence_summarization
from claim_verifier.evidence_summarization import (
    EvidenceSummaryOutput,
    ClaimRelevantExtract,
    summarize_evidence_for_claim,
)
from claim_verifier.nodes.evaluate_evidence import evaluate_evidence_node
from claim_verifier.schemas import ClaimVerifierState, Evidence
from claim_extractor.schemas import ValidatedClaim


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def make_evidence(url, text, title=None):
    return Evidence(url=url, text=text, title=title)


def make_claim(claim_text="The sky is blue."):
    return ValidatedClaim(
        claim_text=claim_text,
        is_complete_declarative=True,
        disambiguated_sentence=claim_text,
        original_sentence=claim_text,
        original_index=0,
    )


# ---------------------------------------------------------------------------
# summarize_evidence_for_claim — config switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_returns_raw_evidence_unchanged_without_llm_call():
    evidence = [make_evidence("https://a.example", "Raw text A.")]

    with patch.dict(
        evidence_summarization.EVIDENCE_SUMMARIZATION_CONFIG, {"enabled": False}
    ), patch(
        "claim_verifier.evidence_summarization.call_llm_with_structured_output",
        new_callable=AsyncMock,
    ) as mock_llm_call, patch(
        "claim_verifier.evidence_summarization.get_llm"
    ) as mock_get_llm:
        result = await summarize_evidence_for_claim("The sky is blue.", evidence)

    mock_llm_call.assert_not_called()
    mock_get_llm.assert_not_called()
    assert result is evidence
    assert result[0].text == "Raw text A."


@pytest.mark.asyncio
async def test_enabled_calls_llm_and_returns_condensed_extracts():
    evidence = [
        make_evidence("https://a.example", "Long raw text about the sky being blue " * 20, title="A"),
        make_evidence("https://b.example", "Long raw text about clouds " * 20, title="B"),
    ]

    mock_response = EvidenceSummaryOutput(
        extracts=[
            ClaimRelevantExtract(source_index=1, extract="The sky is blue."),
            ClaimRelevantExtract(source_index=2, extract="Clouds are white."),
        ]
    )

    with patch.dict(
        evidence_summarization.EVIDENCE_SUMMARIZATION_CONFIG, {"enabled": True}
    ), patch(
        "claim_verifier.evidence_summarization.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ) as mock_llm_call, patch(
        "claim_verifier.evidence_summarization.get_llm", return_value=MagicMock()
    ) as mock_get_llm:
        result = await summarize_evidence_for_claim("The sky is blue.", evidence)

    mock_llm_call.assert_called_once()
    mock_get_llm.assert_called_once()
    # Mid tier is the tier choice for this TG (see module docstring rationale).
    assert mock_get_llm.call_args.kwargs.get("tier") == "mid"

    assert len(result) == 2
    assert result[0].text == "The sky is blue."
    assert result[1].text == "Clouds are white."
    # URL/title attribution always comes from the original item, never the
    # model's output.
    assert result[0].url == "https://a.example"
    assert result[0].title == "A"
    assert result[1].url == "https://b.example"
    assert result[1].title == "B"
    # Condensed text should be much shorter than the raw input.
    assert len(result[0].text) < len(evidence[0].text)


@pytest.mark.asyncio
async def test_empty_evidence_returns_empty_without_llm_call():
    with patch(
        "claim_verifier.evidence_summarization.call_llm_with_structured_output",
        new_callable=AsyncMock,
    ) as mock_llm_call:
        result = await summarize_evidence_for_claim("Some claim.", [])

    mock_llm_call.assert_not_called()
    assert result == []


# ---------------------------------------------------------------------------
# Refuting-content preservation
# ---------------------------------------------------------------------------


def test_system_prompt_instructs_preserving_refuting_content():
    """Prompt-level assertion: the summarizer must be told, explicitly, not
    to drop or soften contradicting evidence relative to supporting evidence.
    This is the guard against the "summarization bias" failure mode named in
    the Phase 03 risk register.
    """
    prompt = evidence_summarization.EVIDENCE_SUMMARIZATION_SYSTEM_PROMPT.lower()

    assert "refut" in prompt or "contradict" in prompt
    assert "equal" in prompt  # equal fidelity/completeness instruction
    assert "support" in prompt


@pytest.mark.asyncio
async def test_refuting_extract_flows_through_intact_to_output():
    """Data-level assertion: when the (mocked) summary contains refuting
    content, that content survives into the returned Evidence list
    unmodified — it must reach the high-tier evaluator, not get dropped.
    """
    evidence = [
        make_evidence("https://supports.example", "Raw supporting content " * 10),
        make_evidence("https://refutes.example", "Raw refuting content " * 10),
    ]

    refuting_extract_text = (
        "Official statistics directly contradict the claim: the reported "
        "figure was actually 12%, not 40% as claimed."
    )
    mock_response = EvidenceSummaryOutput(
        extracts=[
            ClaimRelevantExtract(source_index=1, extract="Supports the claim."),
            ClaimRelevantExtract(source_index=2, extract=refuting_extract_text),
        ]
    )

    with patch.dict(
        evidence_summarization.EVIDENCE_SUMMARIZATION_CONFIG, {"enabled": True}
    ), patch(
        "claim_verifier.evidence_summarization.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("claim_verifier.evidence_summarization.get_llm", return_value=MagicMock()):
        result = await summarize_evidence_for_claim("A disputed statistic.", evidence)

    refuting_result = next(r for r in result if r.url == "https://refutes.example")
    assert refuting_result.text == refuting_extract_text


# ---------------------------------------------------------------------------
# Failure fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_raw_evidence():
    """call_llm_with_structured_output already swallows exceptions and
    returns None on failure (utils/llm.py). Summarization must treat that
    the same way it treats any other failure: fall back to raw evidence,
    never lose the claim, never propagate the error.
    """
    evidence = [make_evidence("https://a.example", "Raw text A.")]

    with patch.dict(
        evidence_summarization.EVIDENCE_SUMMARIZATION_CONFIG, {"enabled": True}
    ), patch(
        "claim_verifier.evidence_summarization.call_llm_with_structured_output",
        new=AsyncMock(return_value=None),
    ), patch("claim_verifier.evidence_summarization.get_llm", return_value=MagicMock()):
        result = await summarize_evidence_for_claim("Some claim.", evidence)

    assert result == evidence
    assert result[0].text == "Raw text A."


@pytest.mark.asyncio
async def test_empty_extracts_falls_back_to_raw_evidence():
    evidence = [make_evidence("https://a.example", "Raw text A.")]
    mock_response = EvidenceSummaryOutput(extracts=[])

    with patch.dict(
        evidence_summarization.EVIDENCE_SUMMARIZATION_CONFIG, {"enabled": True}
    ), patch(
        "claim_verifier.evidence_summarization.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("claim_verifier.evidence_summarization.get_llm", return_value=MagicMock()):
        result = await summarize_evidence_for_claim("Some claim.", evidence)

    assert result == evidence


@pytest.mark.asyncio
async def test_get_llm_construction_failure_falls_back_to_raw_evidence():
    """A synchronous failure building the LLM (e.g. bad provider/tier
    config) must not crash verification either.
    """
    evidence = [make_evidence("https://a.example", "Raw text A.")]

    with patch.dict(
        evidence_summarization.EVIDENCE_SUMMARIZATION_CONFIG, {"enabled": True}
    ), patch(
        "claim_verifier.evidence_summarization.get_llm",
        side_effect=ValueError("Unknown tier"),
    ):
        result = await summarize_evidence_for_claim("Some claim.", evidence)

    assert result == evidence


@pytest.mark.asyncio
async def test_missing_source_index_falls_back_to_raw_text_for_that_source():
    """If the model omits a source from its extracts entirely (the exact
    failure mode that would silently drop refuting evidence), that source's
    original raw text is kept rather than being dropped.
    """
    evidence = [
        make_evidence("https://a.example", "Raw text A."),
        make_evidence("https://b.example", "Raw refuting text B."),
    ]
    # Model only returned an extract for source 1 — source 2 is missing.
    mock_response = EvidenceSummaryOutput(
        extracts=[ClaimRelevantExtract(source_index=1, extract="Condensed A.")]
    )

    with patch.dict(
        evidence_summarization.EVIDENCE_SUMMARIZATION_CONFIG, {"enabled": True}
    ), patch(
        "claim_verifier.evidence_summarization.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch("claim_verifier.evidence_summarization.get_llm", return_value=MagicMock()):
        result = await summarize_evidence_for_claim("Some claim.", evidence)

    assert result[0].text == "Condensed A."
    assert result[1].text == "Raw refuting text B."
    assert result[1].url == "https://b.example"


# ---------------------------------------------------------------------------
# Integration with evaluate_evidence_node
# ---------------------------------------------------------------------------


class _CapturedMessages:
    """Small holder so the mocked evaluation call can record what it saw."""

    value = None


@pytest.mark.asyncio
async def test_evaluate_evidence_node_sends_condensed_evidence_to_high_tier():
    claim = make_claim()
    raw_text_a = "Raw untrimmed text about the sky " * 30
    evidence = [make_evidence("https://a.example", raw_text_a, title="A")]
    state = ClaimVerifierState(claim=claim, evidence=evidence, iteration_count=1)

    condensed = [make_evidence("https://a.example", "Condensed: sky is blue.", title="A")]

    async def _fake_call_llm(llm, output_class, messages, context_desc=""):
        _CapturedMessages.value = messages
        from claim_verifier.nodes.evaluate_evidence import EvidenceEvaluationOutput

        return EvidenceEvaluationOutput(
            verdict="Supported", reasoning="Test reasoning.", influential_source_indices=[1]
        )

    with patch(
        "claim_verifier.nodes.evaluate_evidence.summarize_evidence_for_claim",
        new=AsyncMock(return_value=condensed),
    ) as mock_summarize, patch(
        "claim_verifier.nodes.evaluate_evidence.call_llm_with_structured_output",
        new=AsyncMock(side_effect=_fake_call_llm),
    ), patch(
        "claim_verifier.nodes.evaluate_evidence.get_llm", return_value=MagicMock()
    ):
        result = await evaluate_evidence_node(state)

    mock_summarize.assert_called_once()
    assert mock_summarize.call_args.args[0] == claim.claim_text
    assert mock_summarize.call_args.args[1] == evidence

    sent_human_message = _CapturedMessages.value[1][1]
    assert "Condensed: sky is blue." in sent_human_message
    assert raw_text_a not in sent_human_message

    verdict = result["verdict"]
    assert verdict.result.value == "Supported"


@pytest.mark.asyncio
async def test_evaluate_evidence_node_byte_compatible_when_summarization_disabled():
    """Switch off: evaluate_evidence_node must receive exactly the raw
    evidence it received before this TG — no condensation, no LLM call for
    summarization.
    """
    claim = make_claim()
    raw_text_a = "Raw untrimmed text about the sky."
    evidence = [make_evidence("https://a.example", raw_text_a, title="A")]
    state = ClaimVerifierState(claim=claim, evidence=evidence, iteration_count=1)

    async def _fake_call_llm(llm, output_class, messages, context_desc=""):
        _CapturedMessages.value = messages
        from claim_verifier.nodes.evaluate_evidence import EvidenceEvaluationOutput

        return EvidenceEvaluationOutput(
            verdict="Supported", reasoning="Test reasoning.", influential_source_indices=[1]
        )

    with patch.dict(
        evidence_summarization.EVIDENCE_SUMMARIZATION_CONFIG, {"enabled": False}
    ), patch(
        "claim_verifier.evidence_summarization.call_llm_with_structured_output",
        new_callable=AsyncMock,
    ) as mock_summarize_llm_call, patch(
        "claim_verifier.nodes.evaluate_evidence.call_llm_with_structured_output",
        new=AsyncMock(side_effect=_fake_call_llm),
    ), patch(
        "claim_verifier.nodes.evaluate_evidence.get_llm", return_value=MagicMock()
    ):
        result = await evaluate_evidence_node(state)

    mock_summarize_llm_call.assert_not_called()

    sent_human_message = _CapturedMessages.value[1][1]
    assert raw_text_a in sent_human_message

    verdict = result["verdict"]
    # sources on the verdict are always built from the raw evidence,
    # regardless of the summarization switch.
    assert verdict.sources[0].text == raw_text_a
