"""Tests for the heavy-pipeline orchestration (TG 03.3).

``scripts.run_heavy.run_pipeline`` composes the full heavy pipeline:
parse -> extract (Claimify) -> bind -> vault verify -> triage -> route ->
suggested actions. These tests drive it with **every** LLM/graph call mocked
(no live calls, no dev server) and assert that:

- records flow end to end and claim identity / positions / cite sets survive;
- triage fields and routing decisions are populated;
- ``web_verdict`` stays ``None`` for claims the web never checked (the honest
  identity design from issue #1 — no fabricated web result);
- a no-vault manifest degrades cleanly (vault stages no-op, not error);
- LLM/graph stage failures are recorded per-stage and the run continues;
- the rendered report carries the new Route summary + per-claim triage/routing.

See scripts/run_heavy.py and ingest/gap_report.py.
"""

import json
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import scripts.run_heavy as run_heavy
from claim_extractor.schemas import ValidatedClaim
from claim_verifier.schemas import Evidence, Verdict, VerificationResult
from ingest.alignment import AlignmentOutput
from ingest.routing import RESOLVED, UNVERIFIABLE, route_decision
from ingest.triage import BatchTriageOutput, TriageProposal
from ingest.vault_match import BatchMatchOutput, MatchProposal, VerifyOutput
from ingest.vault_serializer import VaultNote
from scripts.run_heavy import run_pipeline, write_outputs
from utils.claim_record import CitationStatus, ClaimRecord, DraftPosition, RouteVerdict
from utils.run_config import ResourceManifest

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

DRAFT_TEXT = (
    "The sky is blue [[SOURCE-sky]]. "
    "Our model reaches 94 percent accuracy on the test set. "
    "Paris is the capital of France."
)
# parse_draft(DRAFT_TEXT) -> sentence 0 CITED (SOURCE-sky), 1 & 2 CITATION_FREE.


def make_validated_claim(claim_text, original_index):
    return ValidatedClaim(
        claim_text=claim_text,
        is_complete_declarative=True,
        disambiguated_sentence=claim_text,
        original_sentence=claim_text,
        original_index=original_index,
    )


def make_vault_note(name, note_type="web-page", body="Some content.", wikilinks=None):
    return VaultNote(
        name=name,
        note_type=note_type,
        frontmatter={"type": note_type},
        body_sections={"": body},
        wikilinks=wikilinks or [],
        file_path=f"v-research/{name}.md",
    )


async def stub_web_handler(record: ClaimRecord):
    """A web route handler that records a Supported verdict without any LLM."""
    verdict = Verdict(
        claim_text=record.claim_text,
        disambiguated_sentence=record.claim_text,
        original_sentence=record.claim_text,
        original_index=record.position.sentence_index if record.position else 0,
        result=VerificationResult.SUPPORTED,
        reasoning="stub web verdict",
        sources=[Evidence(url="https://example.com/e", text="evidence")],
    )
    record.web_verdict = verdict
    rv = RouteVerdict(
        route="web",
        verdict="Supported",
        reasoning="stub web verdict",
        provenance="https://example.com/e",
        provenance_type="web_url",
    )
    record.route_verdicts.append(rv)
    return rv


def _extractor(validated_claims=None, side_effect=None):
    if side_effect is not None:
        return SimpleNamespace(ainvoke=AsyncMock(side_effect=side_effect))
    return SimpleNamespace(
        ainvoke=AsyncMock(return_value={"validated_claims": validated_claims or []})
    )


DEFAULT_TRIAGE = BatchTriageOutput(
    classifications=[
        TriageProposal(claim_index=0, triage_class="general-factual", citation_expectation="optional", importance=3),
        TriageProposal(claim_index=1, triage_class="novel-result", citation_expectation="not-expected", importance=5),
        TriageProposal(claim_index=2, triage_class="general-factual", citation_expectation="expected", importance=4),
    ]
)


def _stage_patches(
    stack: ExitStack,
    *,
    extractor,
    load_vault=None,
    triage=DEFAULT_TRIAGE,
    alignment=None,
    batch_match=None,
):
    """Enter all stage-level patches; return nothing (mutates via stack)."""
    stack.enter_context(patch.object(run_heavy, "claim_extractor_graph", extractor))
    if load_vault is not None:
        stack.enter_context(patch.object(run_heavy, "load_vault", load_vault))

    stack.enter_context(patch("ingest.triage.get_llm", return_value=MagicMock()))
    stack.enter_context(
        patch("ingest.triage.call_llm_with_structured_output", new=AsyncMock(return_value=triage))
    )
    if alignment is not None:
        stack.enter_context(patch("ingest.alignment.get_llm", return_value=MagicMock()))
        stack.enter_context(
            patch("ingest.alignment.call_llm_with_structured_output", new=AsyncMock(return_value=alignment))
        )
    if batch_match is not None:
        stack.enter_context(patch("ingest.vault_match.get_llm", return_value=MagicMock()))
        stack.enter_context(
            patch("ingest.vault_match.call_llm_with_structured_output", new=AsyncMock(return_value=batch_match))
        )


# ---------------------------------------------------------------------------
# Full heavy run (vault + web), end to end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_heavy_pipeline_flows_end_to_end():
    manifest = ResourceManifest(
        draft_path=Path("draft.md"),
        vault_path=Path("fake-vault"),
        argument_pyramid="test-pyramid",
        web_enabled=True,
    )
    extractor = _extractor(
        [
            make_validated_claim("The sky is blue.", 0),
            make_validated_claim("Our model reaches 94 percent accuracy.", 1),
            make_validated_claim("Paris is the capital of France.", 2),
        ]
    )
    vault_load = MagicMock(return_value=[make_vault_note("SOURCE-sky", body="The sky is blue.")])

    with ExitStack() as stack:
        _stage_patches(
            stack,
            extractor=extractor,
            load_vault=vault_load,
            alignment=AlignmentOutput(
                verdict="vault_supported",
                reasoning="Directly supports.",
                supporting_note="SOURCE-sky",
            ),
            batch_match=BatchMatchOutput(matches=[]),
        )
        records, stage_errors = await run_pipeline(
            DRAFT_TEXT, manifest, route_handlers={"web": stub_web_handler}
        )

    assert stage_errors == []
    assert len(records) == 3

    # Identity, positions and cite sets survived binding.
    assert records[0].claim is not None
    assert records[0].claim.claim_text == "The sky is blue."
    assert records[0].citation_status == CitationStatus.CITED
    assert records[0].cite_set == ["SOURCE-sky"]
    assert records[0].position.sentence_index == 0
    assert records[2].position.sentence_index == 2

    # Cited claim: vault-aligned + resolved, no web check (web_verdict stays None).
    aligned = [rv for rv in records[0].route_verdicts if rv.route == "vault_aligned"]
    assert len(aligned) == 1 and aligned[0].verdict == "vault_supported"
    assert records[0].routing_decision == RESOLVED
    assert records[0].web_verdict is None

    # Novel-result claim: triaged, never web, explicitly unverifiable, no web check.
    assert records[1].triage_class == "novel-result"
    assert records[1].routing_decision == UNVERIFIABLE
    assert records[1].web_verdict is None

    # General-factual, citation-free: routed to web, web verdict now present.
    assert records[2].triage_class == "general-factual"
    assert records[2].routing_decision == route_decision("web")
    assert any(rv.route == "web" for rv in records[2].route_verdicts)
    assert records[2].web_verdict is not None

    # Report renders the new sections.
    from ingest.gap_report import render_gap_report

    report = render_gap_report(records, manifest)
    assert "## Route summary" in report
    assert "Web calls avoided" in report
    assert "**Triage:**" in report
    assert "**Routing:**" in report
    assert "## Vault Improvement Signals" in report


# ---------------------------------------------------------------------------
# Full-vault fallback (Phase 03 milestone review)
# ---------------------------------------------------------------------------

FALLBACK_TRIAGE = BatchTriageOutput(
    classifications=[
        TriageProposal(
            claim_index=0, triage_class="general-factual", citation_expectation="optional", importance=3
        ),
    ]
)


def _fallback_manifest():
    return ResourceManifest(
        draft_path=Path("draft.md"),
        vault_path=Path("fake-vault"),
        argument_pyramid="test-pyramid",
        web_enabled=True,
    )


def _fallback_load_vault(filtered_notes, full_notes):
    """A load_vault stand-in that returns ``filtered_notes`` when called with
    an argument_pyramid filter, and ``full_notes`` for the unfiltered call."""

    def _side_effect(vault_path, argument_pyramid=None, evidence_types=None):
        if argument_pyramid is not None:
            return filtered_notes
        return full_notes

    return MagicMock(side_effect=_side_effect)


@pytest.mark.asyncio
async def test_vault_match_fallback_fires_for_unmatched_claims_only():
    """The filtered (argument_pyramid-tagged) corpus has no matching note for
    a citation-free claim; the note DOES exist in the full vault, just
    untagged. The fallback pass must find it and mark it as a fallback
    match (provenance_type="vault_note_fallback") -- the vault-improvement
    signal the gap report surfaces."""
    extractor = _extractor([make_validated_claim("Our model reaches 94 percent accuracy.", 0)])
    untagged_note = make_vault_note("SOURCE-untagged", body="Reaches 94 percent accuracy.")
    vault_load = _fallback_load_vault(filtered_notes=[], full_notes=[untagged_note])

    llm_responses = [
        BatchMatchOutput(matches=[]),  # pass 1: filtered vault is empty, no proposal
        BatchMatchOutput(  # fallback pass: found it in the full vault
            matches=[MatchProposal(claim_index=0, note_name="SOURCE-untagged", reasoning="Matches.")]
        ),
        VerifyOutput(  # verify_matches on the fallback proposal
            verdict="vault_supported", reasoning="Confirmed.", supporting_note="SOURCE-untagged"
        ),
    ]

    with ExitStack() as stack:
        stack.enter_context(patch.object(run_heavy, "claim_extractor_graph", extractor))
        stack.enter_context(patch.object(run_heavy, "load_vault", vault_load))
        stack.enter_context(patch("ingest.triage.get_llm", return_value=MagicMock()))
        stack.enter_context(
            patch(
                "ingest.triage.call_llm_with_structured_output",
                new=AsyncMock(return_value=FALLBACK_TRIAGE),
            )
        )
        stack.enter_context(patch("ingest.vault_match.get_llm", return_value=MagicMock()))
        mock_llm_call = stack.enter_context(
            patch(
                "ingest.vault_match.call_llm_with_structured_output",
                new=AsyncMock(side_effect=llm_responses),
            )
        )
        records, stage_errors = await run_pipeline(
            "Our model reaches 94 percent accuracy.",
            _fallback_manifest(),
            route_handlers={"web": stub_web_handler},
        )

    assert stage_errors == []
    assert mock_llm_call.call_count == 3

    fallback_verdicts = [
        rv
        for rv in records[0].route_verdicts
        if rv.route == "vault_matched" and rv.provenance_type == "vault_note_fallback"
    ]
    assert len(fallback_verdicts) == 1
    assert fallback_verdicts[0].verdict == "vault_supported"
    assert fallback_verdicts[0].provenance == "SOURCE-untagged"

    # The gap report renders the tagging-gap signal for this note.
    from ingest.gap_report import render_gap_report

    report = render_gap_report(records, _fallback_manifest())
    assert "### Notes matched outside the paper filter" in report
    assert "SOURCE-untagged" in report
    assert "argument_pyramid" in report


@pytest.mark.asyncio
async def test_no_fallback_call_when_all_matched_in_pass1():
    """When the filtered pass already matches every citation-free claim,
    the fallback must not fire at all -- no second batch call."""
    extractor = _extractor([make_validated_claim("Our model reaches 94 percent accuracy.", 0)])
    tagged_note = make_vault_note("SOURCE-tagged", body="Reaches 94 percent accuracy.")
    vault_load = _fallback_load_vault(filtered_notes=[tagged_note], full_notes=[tagged_note])

    llm_responses = [
        BatchMatchOutput(  # pass 1 finds a match immediately
            matches=[MatchProposal(claim_index=0, note_name="SOURCE-tagged", reasoning="Matches.")]
        ),
        VerifyOutput(
            verdict="vault_supported", reasoning="Confirmed.", supporting_note="SOURCE-tagged"
        ),
    ]

    with ExitStack() as stack:
        stack.enter_context(patch.object(run_heavy, "claim_extractor_graph", extractor))
        stack.enter_context(patch.object(run_heavy, "load_vault", vault_load))
        stack.enter_context(patch("ingest.triage.get_llm", return_value=MagicMock()))
        stack.enter_context(
            patch(
                "ingest.triage.call_llm_with_structured_output",
                new=AsyncMock(return_value=FALLBACK_TRIAGE),
            )
        )
        stack.enter_context(patch("ingest.vault_match.get_llm", return_value=MagicMock()))
        mock_llm_call = stack.enter_context(
            patch(
                "ingest.vault_match.call_llm_with_structured_output",
                new=AsyncMock(side_effect=llm_responses),
            )
        )
        records, stage_errors = await run_pipeline(
            "Our model reaches 94 percent accuracy.",
            _fallback_manifest(),
            route_handlers={"web": stub_web_handler},
        )

    assert stage_errors == []
    # Exactly pass-1's two calls (batch propose + verify) -- no fallback call.
    assert mock_llm_call.call_count == 2
    assert all(
        rv.provenance_type != "vault_note_fallback" for rv in records[0].route_verdicts
    )


@pytest.mark.asyncio
async def test_no_fallback_when_config_knob_off():
    """`VAULT_MATCH_FALLBACK_ENABLED=False` must restore the current
    single-pass behavior exactly -- no fallback call even though the
    filtered pass leaves the claim unmatched."""
    extractor = _extractor([make_validated_claim("Our model reaches 94 percent accuracy.", 0)])
    untagged_note = make_vault_note("SOURCE-untagged", body="Reaches 94 percent accuracy.")
    vault_load = _fallback_load_vault(filtered_notes=[], full_notes=[untagged_note])

    llm_responses = [
        BatchMatchOutput(matches=[]),  # pass 1: nothing in the empty filtered vault
    ]

    with ExitStack() as stack:
        stack.enter_context(patch.object(run_heavy, "claim_extractor_graph", extractor))
        stack.enter_context(patch.object(run_heavy, "load_vault", vault_load))
        stack.enter_context(patch.object(run_heavy, "VAULT_MATCH_FALLBACK_ENABLED", False))
        stack.enter_context(patch("ingest.triage.get_llm", return_value=MagicMock()))
        stack.enter_context(
            patch(
                "ingest.triage.call_llm_with_structured_output",
                new=AsyncMock(return_value=FALLBACK_TRIAGE),
            )
        )
        stack.enter_context(patch("ingest.vault_match.get_llm", return_value=MagicMock()))
        mock_llm_call = stack.enter_context(
            patch(
                "ingest.vault_match.call_llm_with_structured_output",
                new=AsyncMock(side_effect=llm_responses),
            )
        )
        records, stage_errors = await run_pipeline(
            "Our model reaches 94 percent accuracy.",
            _fallback_manifest(),
            route_handlers={"web": stub_web_handler},
        )

    assert stage_errors == []
    # Only pass-1's single (empty) batch call -- the config knob suppressed the fallback.
    assert mock_llm_call.call_count == 1
    assert records[0].route_verdicts == [] or all(
        rv.route != "vault_matched" for rv in records[0].route_verdicts
    )


# ---------------------------------------------------------------------------
# No-vault manifest degrades cleanly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_vault_manifest_degrades_cleanly():
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=None, web_enabled=True)
    extractor = _extractor(
        [
            make_validated_claim("The sky is blue.", 0),
            make_validated_claim("Our model reaches 94 percent accuracy.", 1),
            make_validated_claim("Paris is the capital of France.", 2),
        ]
    )
    vault_load = MagicMock(return_value=[make_vault_note("SOURCE-sky")])

    with ExitStack() as stack:
        _stage_patches(stack, extractor=extractor, load_vault=vault_load)
        records, stage_errors = await run_pipeline(
            DRAFT_TEXT, manifest, route_handlers={"web": stub_web_handler}
        )

    # Vault stages did not run at all -> no error, load_vault untouched.
    assert stage_errors == []
    vault_load.assert_not_called()
    assert len(records) == 3
    assert all(
        rv.route not in ("vault_aligned", "vault_matched")
        for r in records
        for rv in r.route_verdicts
    )
    # Triage/routing still ran.
    assert records[1].triage_class == "novel-result"
    assert records[2].routing_decision == route_decision("web")

    from ingest.gap_report import render_gap_report

    report = render_gap_report(records, manifest)
    assert "## Route summary" in report
    assert "## Vault Improvement Signals" not in report
    assert "not configured" in report


# ---------------------------------------------------------------------------
# Stage failures are recorded per-stage; run continues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extraction_failure_records_error_no_crash():
    manifest = ResourceManifest(draft_path=Path("draft.md"), web_enabled=True)
    extractor = _extractor(side_effect=RuntimeError("extractor boom"))

    with ExitStack() as stack:
        _stage_patches(stack, extractor=extractor)
        records, stage_errors = await run_pipeline(DRAFT_TEXT, manifest)

    assert records == []
    assert any(e["stage"] == "extract_claims" for e in stage_errors)


@pytest.mark.asyncio
async def test_vault_load_failure_recorded_run_continues():
    manifest = ResourceManifest(
        draft_path=Path("draft.md"), vault_path=Path("fake-vault"), web_enabled=True
    )
    extractor = _extractor([make_validated_claim("The sky is blue.", 0)])
    vault_load = MagicMock(side_effect=OSError("cannot read vault"))

    with ExitStack() as stack:
        _stage_patches(stack, extractor=extractor, load_vault=vault_load)
        records, stage_errors = await run_pipeline(
            DRAFT_TEXT, manifest, route_handlers={"web": stub_web_handler}
        )

    assert any(e["stage"] == "load_vault" for e in stage_errors)
    # Run still completed: the cited claim got a note_not_in_vault verdict
    # (empty vault) and a suggested action was assigned.
    assert len(records) == 1
    assert records[0].suggested_action is not None
    assert records[0].routing_decision is not None


# ---------------------------------------------------------------------------
# write_outputs
# ---------------------------------------------------------------------------


def test_write_outputs_produces_results_and_report(tmp_path):
    manifest = ResourceManifest(draft_path=Path("draft.md"), vault_path=Path("vault"))
    record = ClaimRecord(
        claim=make_validated_claim("A claim.", 0),
        citation_status=CitationStatus.CITATION_FREE,
        position=DraftPosition(sentence_index=0),
        triage_class="general-factual",
        routing_decision=route_decision("web"),
        routing_reason="general: routed to 'web'",
    )
    from ingest.gap_report import assign_suggested_actions

    assign_suggested_actions([record])

    results_path, report_path = write_outputs(tmp_path, [record], manifest, stage_errors=[])

    assert results_path.exists() and report_path.exists()
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    assert payload["claims"][0]["claim"]["claim_text"] == "A claim."
    assert "## Route summary" in report_path.read_text(encoding="utf-8")
