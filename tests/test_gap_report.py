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
    detect_conflicts,
    render_gap_report,
    serialize_results,
)
from ingest.routing import RESOLVED, route_decision
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


def make_conflict_record(route_verdicts, conflict_flags=None):
    """Bare record for detect_conflicts tests: no web_verdict noise, just
    the route_verdicts list detect_conflicts actually reads."""
    return ClaimRecord(
        citation_status=CitationStatus.CITATION_FREE,
        position=DraftPosition(sentence_index=0),
        route_verdicts=route_verdicts,
        conflict_flags=conflict_flags or [],
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


def test_action_add_citation_when_web_insufficient_citation_free():
    """An insufficient web verdict must not be treated as resolved: a
    citation-free claim with no vault match still needs ADD_CITATION, not
    ADD_VAULT_NOTE."""
    record = make_record(
        "Claim H",
        citation_status=CitationStatus.CITATION_FREE,
        route_verdicts=[],
        web_result=VerificationResult.INSUFFICIENT,
    )

    result = assign_suggested_actions([record])

    assert result[0].suggested_action == SuggestedAction.ADD_CITATION


def test_action_unresolved_when_web_insufficient_cited():
    """Same insufficient web verdict, but the claim is cited (not
    citation-free) with no vault match -> falls through to UNRESOLVED."""
    record = make_record(
        "Claim I",
        citation_status=CitationStatus.CITED,
        route_verdicts=[],
        web_result=VerificationResult.INSUFFICIENT,
    )

    result = assign_suggested_actions([record])

    assert result[0].suggested_action == SuggestedAction.UNRESOLVED


def test_action_add_citation_when_web_conflicting_citation_free():
    """A conflicting web verdict must likewise not be treated as resolved:
    citation-free with no vault match -> ADD_CITATION, not ADD_VAULT_NOTE."""
    record = make_record(
        "Claim J",
        citation_status=CitationStatus.CITATION_FREE,
        route_verdicts=[],
        web_result=VerificationResult.CONFLICTING,
    )

    result = assign_suggested_actions([record])

    assert result[0].suggested_action == SuggestedAction.ADD_CITATION


def test_action_unresolved_when_web_conflicting_cited():
    """Conflicting web verdict, cited claim, no vault match -> UNRESOLVED."""
    record = make_record(
        "Claim K",
        citation_status=CitationStatus.CITED,
        route_verdicts=[],
        web_result=VerificationResult.CONFLICTING,
    )

    result = assign_suggested_actions([record])

    assert result[0].suggested_action == SuggestedAction.UNRESOLVED


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


def test_source_conflict_outranks_individual_verdicts():
    """A source-conflict flag must win REVISE_CLAIM even when the vault
    verdict alone (vault_supported) would otherwise resolve to NONE."""
    record = make_conflict_record(
        [
            RouteVerdict(
                route="vault_aligned", verdict="vault_supported", provenance="NOTE-h"
            )
        ],
        conflict_flags=["source-conflict"],
    )

    result = assign_suggested_actions([record])

    assert result[0].suggested_action == SuggestedAction.REVISE_CLAIM


# ---------------------------------------------------------------------------
# detect_conflicts
# ---------------------------------------------------------------------------


def test_source_conflict_web_refutes_vault_supports():
    record = make_conflict_record(
        [
            RouteVerdict(
                route="vault_aligned", verdict="vault_supported", provenance="NOTE-a"
            ),
            RouteVerdict(
                route="web", verdict="Refuted", provenance="https://example.com/a"
            ),
        ]
    )

    detect_conflicts([record])

    assert record.conflict_flags == ["source-conflict"]


def test_source_conflict_web_supports_vault_refutes():
    record = make_conflict_record(
        [
            RouteVerdict(
                route="vault_aligned", verdict="vault_contradicted", provenance="NOTE-b"
            ),
            RouteVerdict(
                route="web", verdict="Supported", provenance="https://example.com/b"
            ),
        ]
    )

    detect_conflicts([record])

    assert record.conflict_flags == ["source-conflict"]


def test_vault_corpus_check_needed():
    record = make_conflict_record(
        [
            RouteVerdict(
                route="vault_aligned", verdict="vault_supported", provenance="NOTE-c"
            ),
            RouteVerdict(
                route="corpus", verdict="corpus_contradicted", provenance="doc-1"
            ),
        ]
    )

    detect_conflicts([record])

    assert record.conflict_flags == ["vault-corpus-check-needed"]


def test_both_flags_possible():
    record = make_conflict_record(
        [
            RouteVerdict(
                route="vault_aligned", verdict="vault_supported", provenance="NOTE-d"
            ),
            RouteVerdict(
                route="corpus", verdict="corpus_contradicted", provenance="doc-2"
            ),
            RouteVerdict(
                route="web", verdict="Refuted", provenance="https://example.com/d"
            ),
        ]
    )

    detect_conflicts([record])

    assert set(record.conflict_flags) == {"source-conflict", "vault-corpus-check-needed"}


def test_silent_never_triggers_flag():
    record = make_conflict_record(
        [
            RouteVerdict(
                route="vault_aligned", verdict="vault_supported", provenance="NOTE-e"
            ),
            RouteVerdict(
                route="corpus", verdict="corpus_insufficient", provenance="doc-3"
            ),
        ]
    )

    detect_conflicts([record])

    assert record.conflict_flags == []


def test_no_conflict_all_support():
    record = make_conflict_record(
        [
            RouteVerdict(
                route="vault_aligned", verdict="vault_supported", provenance="NOTE-f"
            ),
            RouteVerdict(
                route="web", verdict="Supported", provenance="https://example.com/f"
            ),
        ]
    )

    detect_conflicts([record])

    assert record.conflict_flags == []


def test_no_verdicts_no_flags():
    record = make_conflict_record([])

    detect_conflicts([record])

    assert record.conflict_flags == []


def test_unknown_verdict_treated_as_silent():
    record = make_conflict_record(
        [
            RouteVerdict(
                route="vault_aligned", verdict="vault_supported", provenance="NOTE-g"
            ),
            RouteVerdict(
                route="web",
                verdict="some_unrecognized_value",
                provenance="https://example.com/g",
            ),
        ]
    )

    detect_conflicts([record])

    assert record.conflict_flags == []


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


def test_source_conflict_rendered_in_claim_detail():
    record = make_record(
        "Conflicted claim.",
        citation_status=CitationStatus.CITED,
        route_verdicts=[
            RouteVerdict(
                route="vault_aligned",
                verdict="vault_supported",
                provenance="NOTE-conflict",
            ),
            RouteVerdict(
                route="web",
                verdict="Refuted",
                provenance="https://example.com/conflict",
            ),
        ],
        web_result=VerificationResult.REFUTED,
    )
    detect_conflicts([record])
    assign_suggested_actions([record])
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([record], manifest)

    assert "Source conflict" in report or "source-conflict" in report.lower()
    assert "NOTE-conflict" in report
    assert "https://example.com/conflict" in report


def test_vault_corpus_check_in_improvement_signals():
    record = make_record(
        "Mismatched claim.",
        citation_status=CitationStatus.CITED,
        route_verdicts=[
            RouteVerdict(
                route="vault_aligned",
                verdict="vault_supported",
                provenance="NOTE-mismatch",
            ),
            RouteVerdict(
                route="corpus", verdict="corpus_contradicted", provenance="doc-mismatch"
            ),
        ],
    )
    detect_conflicts([record])
    assign_suggested_actions([record])
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([record], manifest)

    assert "## Vault Improvement Signals" in report
    assert "vault says vault_supported" in report
    assert "corpus says corpus_contradicted" in report
    assert "re-read the source against your note" in report


def test_single_lineage_annotation():
    record = make_record(
        "Vault-only resolved claim.",
        citation_status=CitationStatus.CITED,
        route_verdicts=[
            RouteVerdict(
                route="vault_aligned", verdict="vault_supported", provenance="NOTE-solo"
            ),
        ],
    )
    detect_conflicts([record])
    assign_suggested_actions([record])
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([record], manifest)

    assert "(single-lineage)" in report


def test_light_profile_unchanged():
    """No vault, no corpus -> report unchanged (no new conflict/single-lineage
    sections), matching Phase 01's report format exactly."""
    record = make_record("A claim without a vault.", citation_status=CitationStatus.CITATION_FREE)
    detect_conflicts([record])
    assign_suggested_actions([record])
    manifest = ResourceManifest(draft_path=Path("draft.md"))

    report = render_gap_report([record], manifest)

    assert "source-conflict" not in report.lower()
    assert "single-lineage" not in report
    assert "Vault Improvement Signals" not in report


# ---------------------------------------------------------------------------
# _render_route_summary web/corpus call counting (TG M2)
# ---------------------------------------------------------------------------
#
# ``route_verdicts`` is ground truth for handler invocations -- a record's
# ``routing_decision`` only reflects the route ``decide_route``/cascade
# settled on. D4/D5/D10 cross-checks (``ingest.routing.apply_cross_checks``)
# invoke route handlers directly and append ``RouteVerdict`` entries WITHOUT
# touching ``routing_decision``, so a vault-resolved record can carry a real
# web (or corpus) call that a routing_decision-only count would miss.


def make_routed_record(
    claim_text,
    routing_decision,
    route_verdicts,
    citation_status=CitationStatus.CITATION_FREE,
    importance=None,
    triage_class=None,
    cite_set=None,
):
    return ClaimRecord(
        citation_status=citation_status,
        position=DraftPosition(sentence_index=0),
        route_verdicts=route_verdicts,
        routing_decision=routing_decision,
        triage_class=triage_class,
        importance=importance,
        cite_set=cite_set or [],
    )


def test_cross_check_web_verdict_counted_despite_vault_routing_decision():
    """A vault-resolved record carrying a web RouteVerdict from a D5/D10
    cross-check must be counted as a web call -- the bug this TG fixes."""
    record = make_routed_record(
        "Important supported claim.",
        routing_decision=RESOLVED,
        route_verdicts=[
            RouteVerdict(route="vault_aligned", verdict="vault_supported", provenance="NOTE-1"),
            RouteVerdict(route="web", verdict="Supported", provenance="https://example.com/a"),
        ],
        importance=5,
    )
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([record], manifest)

    assert "Web calls made this run: 1" in report
    assert "0 via routing, 1 via cross-checks" in report


def test_conflict_demo_shape_nine_vault_resolved_web_cross_checks():
    """Reproduces the live conflict-demo run: 9 vault-resolved claims, each
    carrying one web cross-check RouteVerdict. Previously reported 0 web
    calls; must now report 9, all via cross-checks."""
    records = [
        make_routed_record(
            f"Claim {i}",
            routing_decision=RESOLVED,
            route_verdicts=[
                RouteVerdict(
                    route="vault_aligned", verdict="vault_supported", provenance=f"NOTE-{i}"
                ),
                RouteVerdict(
                    route="web", verdict="Supported", provenance=f"https://example.com/{i}"
                ),
            ],
            importance=5,
        )
        for i in range(9)
    ]
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report(records, manifest)

    assert "Web calls made this run: 9" in report
    assert "0 via routing, 9 via cross-checks" in report


def test_mixed_routing_and_cross_check_web_calls_sum():
    routed = make_routed_record(
        "Routed to web directly.",
        routing_decision=route_decision("web"),
        route_verdicts=[
            RouteVerdict(route="web", verdict="Refuted", provenance="https://example.com/b"),
        ],
    )
    cross_checked = make_routed_record(
        "Vault-resolved, web cross-checked.",
        routing_decision=RESOLVED,
        route_verdicts=[
            RouteVerdict(route="vault_matched", verdict="vault_supported", provenance="NOTE-2"),
            RouteVerdict(route="web", verdict="Supported", provenance="https://example.com/c"),
        ],
        importance=5,
    )
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([routed, cross_checked], manifest)

    assert "Web calls made this run: 2" in report
    assert "1 via routing, 1 via cross-checks" in report


def test_d4_corpus_cross_check_counted_and_broken_out():
    record = make_routed_record(
        "Cited, vault-resolved, corpus cross-checked.",
        routing_decision=RESOLVED,
        citation_status=CitationStatus.CITED,
        cite_set=["NOTE-3"],
        route_verdicts=[
            RouteVerdict(route="vault_aligned", verdict="vault_supported", provenance="NOTE-3"),
            RouteVerdict(route="corpus", verdict="corpus_supported", provenance="doc-3"),
        ],
        importance=5,
    )
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([record], manifest)

    assert "Corpus calls made this run: 1" in report
    assert "0 via routing, 1 via cross-checks" in report


def test_no_double_count_when_routed_handler_appended_its_own_verdict():
    """The normal (non-cross-check) case: routing_decision is route-web and
    the web handler appended exactly one RouteVerdict for it -- must count
    once, not twice."""
    record = make_routed_record(
        "Normally web-routed claim.",
        routing_decision=route_decision("web"),
        route_verdicts=[
            RouteVerdict(route="web", verdict="Supported", provenance="https://example.com/d"),
        ],
    )
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([record], manifest)

    assert "Web calls made this run: 1" in report
    assert "1 via routing, 0 via cross-checks" in report


def test_none_routing_decision_web_verdict_still_counted():
    """``routing_decision`` can be None (e.g. a hand-built record, or a
    field left unset); ``route_name_from_decision`` on it must not crash,
    and any web verdict present is still a real invocation."""
    record = make_routed_record(
        "No routing decision recorded.",
        routing_decision=None,
        route_verdicts=[
            RouteVerdict(route="web", verdict="Supported", provenance="https://example.com/e"),
        ],
        triage_class="general-factual",
    )
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([record], manifest)

    assert "Web calls made this run: 1" in report
    assert "0 via routing, 1 via cross-checks" in report


def test_multiple_web_verdicts_on_one_record_each_counted():
    """A cascade-silent web attempt followed by a cross-check web call on
    the SAME record -- both are real invocations and both must count."""
    record = make_routed_record(
        "Escalated then cross-checked.",
        routing_decision=RESOLVED,
        route_verdicts=[
            RouteVerdict(
                route="web",
                verdict="Insufficient Information",
                provenance="https://example.com/f",
            ),
            RouteVerdict(route="web", verdict="Supported", provenance="https://example.com/g"),
        ],
        importance=5,
    )
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([record], manifest)

    assert "Web calls made this run: 2" in report


def test_handler_error_verdicts_counted_as_attempted_invocation():
    """A ``handler_error`` synthetic verdict (``execute_routing``'s failure
    path) still represents a real, attempted route-handler call."""
    record = make_routed_record(
        "Web handler raised.",
        routing_decision=route_decision("web"),
        route_verdicts=[
            RouteVerdict(route="web", verdict="handler_error", reasoning="Handler raised: boom"),
        ],
    )
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([record], manifest)

    assert "Web calls made this run: 1" in report
    assert "1 via routing, 0 via cross-checks" in report


def test_route_summary_caveat_about_invocations_vs_searches():
    """The report must disclose that these are handler invocations, not raw
    searches -- one web invocation can run up to 5 search iterations."""
    record = make_routed_record(
        "Any claim.",
        routing_decision=route_decision("web"),
        route_verdicts=[RouteVerdict(route="web", verdict="Supported")],
    )
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))

    report = render_gap_report([record], manifest)

    assert "invocation" in report.lower()
    assert "5 search iteration" in report.lower()


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
