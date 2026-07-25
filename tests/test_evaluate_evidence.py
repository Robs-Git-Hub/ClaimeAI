"""Tests for the evaluate_evidence node's zero-evidence / failure handling
(TG M1).

The web-evidence evaluator (claim_verifier/nodes/evaluate_evidence.py) can
express four verdicts: Supported, Refuted, Insufficient Information, and
Conflicting Evidence. Before this fix, ``VerificationResult`` only declared
the first two, so:

- the LLM-failure fallback defaulted to REFUTED,
- an unparseable/garbage verdict string from the LLM also defaulted to
  REFUTED (the ``ValueError`` catch), and
- a zero-evidence claim (e.g. a dead search provider returning no results)
  still went to a high-tier LLM call and could come back Refuted.

Observed live: a dead search provider produced false "Refuted" verdicts for
claims with no evidence at all. This file locks in the fix: empty evidence
short-circuits to INSUFFICIENT without an LLM call, and every failure path
defaults to INSUFFICIENT instead of REFUTED.

All LLM calls are mocked — no live calls, no network.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claim_extractor.schemas import ValidatedClaim
from claim_verifier.nodes.evaluate_evidence import (
    EvidenceEvaluationOutput,
    evaluate_evidence_node,
)
from claim_verifier.schemas import ClaimVerifierState, Evidence, VerificationResult
from fact_checker.nodes.generate_report import generate_report_node
from fact_checker.schemas import State


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


def make_verdict(result, claim_text="Claim."):
    from claim_verifier.schemas import Verdict

    return Verdict(
        claim_text=claim_text,
        disambiguated_sentence=claim_text,
        original_sentence=claim_text,
        original_index=0,
        result=result,
        reasoning="Test.",
        sources=[],
    )


# ---------------------------------------------------------------------------
# VerificationResult enum — new members
# ---------------------------------------------------------------------------


def test_insufficient_information_parses():
    result = VerificationResult("Insufficient Information")
    assert result is VerificationResult.INSUFFICIENT
    assert result.value == "Insufficient Information"


def test_conflicting_evidence_parses():
    result = VerificationResult("Conflicting Evidence")
    assert result is VerificationResult.CONFLICTING
    assert result.value == "Conflicting Evidence"


# ---------------------------------------------------------------------------
# Empty evidence short-circuit (cost win: skip the LLM call, don't downgrade
# to a cheaper model)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_evidence_returns_insufficient_without_llm_call():
    claim = make_claim()
    state = ClaimVerifierState(claim=claim, evidence=[], iteration_count=1)

    with patch(
        "claim_verifier.nodes.evaluate_evidence.call_llm_with_structured_output",
        new_callable=AsyncMock,
    ) as mock_llm_call, patch(
        "claim_verifier.nodes.evaluate_evidence.get_llm", return_value=MagicMock()
    ) as mock_get_llm:
        result = await evaluate_evidence_node(state)

    mock_llm_call.assert_not_called()
    verdict = result["verdict"]
    assert verdict.result == VerificationResult.INSUFFICIENT
    assert verdict.sources == []
    # get_llm is also skipped — no point constructing a model we never call.
    mock_get_llm.assert_not_called()


# ---------------------------------------------------------------------------
# LLM structured-output failure (returns falsy)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_failure_returns_insufficient_not_refuted():
    claim = make_claim()
    evidence = [make_evidence("https://a.example", "Some evidence text.")]
    state = ClaimVerifierState(claim=claim, evidence=evidence, iteration_count=1)

    with patch(
        "claim_verifier.nodes.evaluate_evidence.summarize_evidence_for_claim",
        new=AsyncMock(return_value=evidence),
    ), patch(
        "claim_verifier.nodes.evaluate_evidence.call_llm_with_structured_output",
        new=AsyncMock(return_value=None),
    ), patch(
        "claim_verifier.nodes.evaluate_evidence.get_llm", return_value=MagicMock()
    ):
        result = await evaluate_evidence_node(state)

    verdict = result["verdict"]
    assert verdict.result == VerificationResult.INSUFFICIENT
    assert verdict.result != VerificationResult.REFUTED


# ---------------------------------------------------------------------------
# Verdict-string parsing from the LLM response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_returns_insufficient_information_string():
    claim = make_claim()
    evidence = [make_evidence("https://a.example", "Some evidence text.")]
    state = ClaimVerifierState(claim=claim, evidence=evidence, iteration_count=1)

    mock_response = EvidenceEvaluationOutput(
        verdict="Insufficient Information",
        reasoning="Evidence is too thin to decide.",
        influential_source_indices=[],
    )

    with patch(
        "claim_verifier.nodes.evaluate_evidence.summarize_evidence_for_claim",
        new=AsyncMock(return_value=evidence),
    ), patch(
        "claim_verifier.nodes.evaluate_evidence.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch(
        "claim_verifier.nodes.evaluate_evidence.get_llm", return_value=MagicMock()
    ):
        result = await evaluate_evidence_node(state)

    assert result["verdict"].result == VerificationResult.INSUFFICIENT


@pytest.mark.asyncio
async def test_llm_returns_conflicting_evidence_string():
    claim = make_claim()
    evidence = [make_evidence("https://a.example", "Some evidence text.")]
    state = ClaimVerifierState(claim=claim, evidence=evidence, iteration_count=1)

    mock_response = EvidenceEvaluationOutput(
        verdict="Conflicting Evidence",
        reasoning="Reliable sources disagree.",
        influential_source_indices=[],
    )

    with patch(
        "claim_verifier.nodes.evaluate_evidence.summarize_evidence_for_claim",
        new=AsyncMock(return_value=evidence),
    ), patch(
        "claim_verifier.nodes.evaluate_evidence.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch(
        "claim_verifier.nodes.evaluate_evidence.get_llm", return_value=MagicMock()
    ):
        result = await evaluate_evidence_node(state)

    assert result["verdict"].result == VerificationResult.CONFLICTING


@pytest.mark.asyncio
async def test_llm_returns_unknown_garbage_string_defaults_to_insufficient():
    """An unparseable verdict string must never silently become REFUTED —
    that was the original bug's second failure path."""
    claim = make_claim()
    evidence = [make_evidence("https://a.example", "Some evidence text.")]
    state = ClaimVerifierState(claim=claim, evidence=evidence, iteration_count=1)

    mock_response = MagicMock()
    mock_response.verdict = "Totally Not A Real Verdict"
    mock_response.reasoning = "garbage"
    mock_response.influential_source_indices = []

    with patch(
        "claim_verifier.nodes.evaluate_evidence.summarize_evidence_for_claim",
        new=AsyncMock(return_value=evidence),
    ), patch(
        "claim_verifier.nodes.evaluate_evidence.call_llm_with_structured_output",
        new=AsyncMock(return_value=mock_response),
    ), patch(
        "claim_verifier.nodes.evaluate_evidence.get_llm", return_value=MagicMock()
    ):
        result = await evaluate_evidence_node(state)

    verdict = result["verdict"]
    assert verdict.result == VerificationResult.INSUFFICIENT
    assert verdict.result != VerificationResult.REFUTED


# ---------------------------------------------------------------------------
# generate_report_node — verdict counts must cover all VerificationResult
# members, not just SUPPORTED/REFUTED
# ---------------------------------------------------------------------------


class TestGenerateReportVerdictCounts:
    @pytest.mark.asyncio
    async def test_counts_cover_all_verdict_types(self):
        state = State(
            answer="Some answer text.",
            verification_results=[
                make_verdict(VerificationResult.SUPPORTED, "c1"),
                make_verdict(VerificationResult.REFUTED, "c2"),
                make_verdict(VerificationResult.INSUFFICIENT, "c3"),
                make_verdict(VerificationResult.CONFLICTING, "c4"),
            ],
        )

        result = await generate_report_node(state)
        report = result["final_report"]

        assert report.claims_verified == 4
        assert "1 supported" in report.summary.lower()
        assert "1 refuted" in report.summary.lower()
        assert "insufficient" in report.summary.lower()
        assert "conflicting" in report.summary.lower()

    @pytest.mark.asyncio
    async def test_zero_counts_for_insufficient_and_conflicting_omitted(self):
        """When there are no insufficient/conflicting verdicts, the summary
        need not mention them — only nonzero categories are called out."""
        state = State(
            answer="Some answer text.",
            verification_results=[
                make_verdict(VerificationResult.SUPPORTED, "c1"),
                make_verdict(VerificationResult.REFUTED, "c2"),
            ],
        )

        result = await generate_report_node(state)
        report = result["final_report"]

        assert "1 supported" in report.summary.lower()
        assert "1 refuted" in report.summary.lower()
        assert "insufficient" not in report.summary.lower()
        assert "conflicting" not in report.summary.lower()

    @pytest.mark.asyncio
    async def test_total_verified_equals_sum_over_all_verdicts(self):
        state = State(
            answer="Some answer text.",
            verification_results=[
                make_verdict(VerificationResult.SUPPORTED, "c1"),
                make_verdict(VerificationResult.SUPPORTED, "c2"),
                make_verdict(VerificationResult.INSUFFICIENT, "c3"),
                make_verdict(VerificationResult.CONFLICTING, "c4"),
                make_verdict(VerificationResult.REFUTED, "c5"),
            ],
        )

        result = await generate_report_node(state)
        report = result["final_report"]

        assert report.claims_verified == 5
        assert "5 claims verified" in report.summary.lower() or "of 5 claims" in report.summary.lower()
