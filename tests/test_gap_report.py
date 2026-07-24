"""Tests for the gap report (TG 02.6).

``assign_suggested_actions`` is a pure, synchronous function that computes a
`SuggestedAction` for each `ClaimRecord` from its web/vault verdicts.
``render_gap_report`` renders the human-readable markdown report;
``serialize_results`` produces the machine-readable results.json payload.

See ingest/gap_report.py.
"""

from pathlib import Path

from claim_verifier.schemas import Verdict, VerificationResult
from ingest.gap_report import (
    assign_suggested_actions,
    render_gap_report,
    serialize_results,
)
from utils.claim_record import (
    CitationStatus,
    ClaimRecord,
    DraftPosition,
    RouteVerdict,
    SuggestedAction,
)
from utils.run_config import ResourceManifest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def make_verdict(claim_text, result=VerificationResult.SUPPORTED):
    return Verdict(
        claim_text=claim_text,
        disambiguated_sentence=claim_text,
        original_sentence=claim_text,
        original_index=0,
        result=result,
        reasoning="Test.",
        sources=[],
    )


def make_record(
    claim_text,
    citation_status=CitationStatus.CITATION_FREE,
    route_verdicts=None,
    web_result=VerificationResult.SUPPORTED,
):
    return ClaimRecord(
        web_verdict=make_verdict(claim_text, web_result),
        citation_status=citation_status,
        position=DraftPosition(sentence_index=0),
        route_verdicts=route_verdicts or [],
    )


# ---------------------------------------------------------------------------
# assign_suggested_actions
# ---------------------------------------------------------------------------


def test_action_none_when_vault_supported():
    record = make_record(
        "Claim A",
        citation_status=CitationStatus.CITED,
        route_verdicts=[
            RouteVerdict(
                route="vault_aligned", verdict="vault_supported", provenance="SOURCE-a"
            )
        ],
    )

    result = assign_suggested_actions([record])

    assert result[0].suggested_action == SuggestedAction.NONE


def test_action_revise_when_contradicted():
    record = make_record(
        "Claim B",
        citation_status=CitationStatus.CITATION_FREE,
        route_verdicts=[
            RouteVerdict(
                route="vault_matched", verdict="vault_contradicted", provenance="NOTE-b"
            )
        ],
    )

    result = assign_suggested_actions([record])

    assert result[0].suggested_action == SuggestedAction.REVISE_CLAIM


def test_action_fix_citation_when_miscite():
    record = make_record(
        "Claim C",
        citation_status=CitationStatus.CITED,
        route_verdicts=[
            RouteVerdict(
                route="vault_aligned", verdict="not_supported", provenance="SOURCE-c"
            )
        ],
    )

    result = assign_suggested_actions([record])

    assert result[0].suggested_action == SuggestedAction.FIX_CITATION


def test_action_add_vault_note_web_only():
    record = make_record(
        "Claim D",
        citation_status=CitationStatus.CITATION_FREE,
        route_verdicts=[],
        web_result=VerificationResult.SUPPORTED,
    )

    result = assign_suggested_actions([record])

    assert result[0].suggested_action == SuggestedAction.ADD_VAULT_NOTE


def test_action_add_citation_free_no_match():
    record = make_record(
        "Claim E",
        citation_status=CitationStatus.CITATION_FREE,
        route_verdicts=[
            RouteVerdict(
                route="vault_matched", verdict="no_vault_match", provenance=None
            )
        ],
        web_result=VerificationResult.REFUTED,
    )

    result = assign_suggested_actions([record])

    assert result[0].suggested_action == SuggestedAction.ADD_CITATION


def test_action_unresolved():
    record = ClaimRecord(
        web_verdict=None,
        citation_status=CitationStatus.CITED,
        position=DraftPosition(sentence_index=0),
        route_verdicts=[],
    )

    result = assign_suggested_actions([record])

    assert result[0].suggested_action == SuggestedAction.UNRESOLVED


def test_action_contradicted_overrides_supported():
    record = make_record(
        "Claim G",
        citation_status=CitationStatus.CITED,
        route_verdicts=[
            RouteVerdict(
                route="vault_aligned", verdict="vault_supported", provenance="SOURCE-g1"
            ),
            RouteVerdict(
                route="vault_matched",
                verdict="vault_contradicted",
                provenance="SOURCE-g2",
            ),
        ],
    )

    result = assign_suggested_actions([record])

    assert result[0].suggested_action == SuggestedAction.REVISE_CLAIM


# ---------------------------------------------------------------------------
# render_gap_report
# ---------------------------------------------------------------------------


def test_report_contains_summary_table():
    records = [
        make_record(
            "Claim 1",
            citation_status=CitationStatus.CITED,
            route_verdicts=[
                RouteVerdict(
                    route="vault_aligned",
                    verdict="vault_supported",
                    provenance="SOURCE-1",
                )
            ],
        ),
        make_record(
            "Claim 2",
            citation_status=CitationStatus.CITATION_FREE,
            web_result=VerificationResult.REFUTED,
        ),
    ]
    assign_suggested_actions(records)
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report(records, manifest)

    assert "## Summary" in report
    assert "| Action | Count |" in report
    assert "No action needed" in report
    assert "Fix citation (miscite)" in report
    assert "Add citation" in report
    assert "Add vault note" in report
    assert "Revise claim" in report
    assert "Unresolved" in report


def test_report_contains_claim_details():
    record = make_record(
        "The sky is blue.",
        citation_status=CitationStatus.CITED,
        route_verdicts=[
            RouteVerdict(
                route="vault_aligned",
                verdict="vault_supported",
                provenance="SOURCE-sky",
                reasoning="Matches the cited note.",
            ),
        ],
    )
    assign_suggested_actions([record])
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([record], manifest)

    assert "The sky is blue." in report
    assert "**Status:** cited" in report
    assert "vault_aligned" in report
    assert "vault_supported" in report
    assert "provenance: SOURCE-sky" in report
    assert "Matches the cited note." in report
    assert "**Suggested action:**" in report


def test_report_vault_improvement_signals():
    record_missing = make_record(
        "Claim about a missing note.",
        citation_status=CitationStatus.CITED,
        route_verdicts=[
            RouteVerdict(
                route="vault_aligned",
                verdict="note_not_in_vault",
                provenance="SOURCE-missing",
            )
        ],
    )
    record_thin = make_record(
        "Claim about a thin note.",
        citation_status=CitationStatus.CITED,
        route_verdicts=[
            RouteVerdict(
                route="vault_aligned",
                verdict="insufficient_vault_content",
                provenance="SOURCE-thin",
            )
        ],
    )
    record_web_only = make_record(
        "Claim supported only by web evidence.",
        citation_status=CitationStatus.CITATION_FREE,
        route_verdicts=[],
        web_result=VerificationResult.SUPPORTED,
    )
    records = [record_missing, record_thin, record_web_only]
    assign_suggested_actions(records)
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report(records, manifest)

    assert "## Vault Improvement Signals" in report
    assert "### Notes not in vault" in report
    assert "SOURCE-missing" in report
    assert "claim #1" in report
    assert "### Notes with insufficient content" in report
    assert "SOURCE-thin" in report
    assert "claim #2" in report
    assert "### Claims supported by web only (vault gap)" in report
    assert "Claim #3" in report
    assert "add vault note" in report


def test_report_fallback_tagging_signal():
    """A claim matched by the full-vault fallback pass (Phase 03 milestone
    review) is marked with provenance_type="vault_note_fallback" -- the
    report must surface it as a tagging gap for the vault owner."""
    record_fallback = make_record(
        "Claim matched outside the paper filter.",
        citation_status=CitationStatus.CITATION_FREE,
        route_verdicts=[
            RouteVerdict(
                route="vault_matched",
                verdict="vault_supported",
                provenance="SOURCE-untagged",
                provenance_type="vault_note_fallback",
            )
        ],
    )
    record_normal = make_record(
        "Claim matched inside the paper filter.",
        citation_status=CitationStatus.CITATION_FREE,
        route_verdicts=[
            RouteVerdict(
                route="vault_matched",
                verdict="vault_supported",
                provenance="SOURCE-tagged",
                provenance_type="vault_note",
            )
        ],
    )
    records = [record_fallback, record_normal]
    assign_suggested_actions(records)
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report(records, manifest)

    assert "### Notes matched outside the paper filter" in report
    assert "SOURCE-untagged" in report
    assert "argument_pyramid" in report
    assert "matched claim #1" in report
    assert "SOURCE-tagged" not in report.split("### Notes matched outside the paper filter")[1].split(
        "###"
    )[0]


def test_report_no_fallback_signal_when_no_fallback_matches():
    record = make_record(
        "Claim matched normally.",
        citation_status=CitationStatus.CITATION_FREE,
        route_verdicts=[
            RouteVerdict(
                route="vault_matched",
                verdict="vault_supported",
                provenance="SOURCE-tagged",
                provenance_type="vault_note",
            )
        ],
    )
    assign_suggested_actions([record])
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([record], manifest)

    section = report.split("### Notes matched outside the paper filter")[1].split("###")[0]
    assert "- None" in section


def test_report_no_vault_section_when_no_vault():
    record = make_record(
        "Claim without a vault.", citation_status=CitationStatus.CITATION_FREE
    )
    assign_suggested_actions([record])
    manifest = ResourceManifest(draft_path=Path("draft.md"))

    report = render_gap_report([record], manifest)

    assert "Vault Improvement Signals" not in report
    assert "Route verdicts" not in report
    assert "not configured" in report


def test_report_header_includes_unparsed_citation_count_when_nonzero():
    """The header must account for every claim: cited + citation-free +
    unparsed-citation should equal the total, so a nonzero unparsed count
    (a wikilink the binder couldn't parse) must be visible, not silently
    folded into a total that doesn't otherwise add up."""
    records = [
        make_record("Cited claim.", citation_status=CitationStatus.CITED),
        make_record("Citation-free claim.", citation_status=CitationStatus.CITATION_FREE),
        make_record(
            "Unparsed citation claim.",
            citation_status=CitationStatus.UNPARSED_CITATION,
        ),
        make_record(
            "Another unparsed citation claim.",
            citation_status=CitationStatus.UNPARSED_CITATION,
        ),
    ]
    assign_suggested_actions(records)
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report(records, manifest)

    assert "Claims: 4 | Cited: 1 | Citation-free: 1 | Unparsed citation: 2" in report


def test_report_header_omits_unparsed_citation_when_zero():
    """No unparsed-citation claims -> header stays in its original,
    already-tested-elsewhere form (no dangling ' | Unparsed citation: 0')."""
    record = make_record("Claim.", citation_status=CitationStatus.CITATION_FREE)
    assign_suggested_actions([record])
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([record], manifest)

    assert "Unparsed citation" not in report
    assert "Claims: 1 | Cited: 0 | Citation-free: 1" in report


def test_report_escapes_pipes():
    record = make_record("A claim with a | pipe in it.")
    assign_suggested_actions([record])
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([record], manifest)

    assert "a | pipe" not in report
    assert "a \\| pipe" in report


# ---------------------------------------------------------------------------
# serialize_results
# ---------------------------------------------------------------------------


def test_serialize_round_trip():
    record = make_record("Claim to serialize.")

    dumped = serialize_results([record])

    assert isinstance(dumped, list)
    assert len(dumped) == 1
    rebuilt = ClaimRecord.model_validate(dumped[0])
    assert rebuilt.web_verdict.claim_text == "Claim to serialize."


def test_serialize_empty():
    assert serialize_results([]) == []
