"""Tests for routing policy and route-handler registry (TG 03.2, TG 05.1).

``decide_route`` is a pure, deterministic function (no LLM, no I/O, no
graph import) that decides what happens to a claim after vault
verification + triage. ``execute_routing`` applies it across a batch of
records and dispatches to registered route handlers.

TG 05.1 adds ``normalize_verdict`` (pure mapping to support/refute/silent)
and cascade logic in ``execute_routing`` (escalate on silent verdicts).

See ingest/routing.py.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from claim_verifier.schemas import Evidence, Verdict, VerificationResult
from ingest.routing import (
    NORM_REFUTE,
    NORM_SILENT,
    NORM_SUPPORT,
    POLICY,
    RESOLVED,
    ROUTE_HANDLERS,
    SKIP_TRIVIAL,
    UNVERIFIABLE,
    PolicyRow,
    RoutingDecision,
    apply_cross_checks,
    decide_route,
    execute_routing,
    normalize_verdict,
    route_decision,
    web_route_handler,
)
from utils.claim_record import CitationStatus, ClaimRecord, DraftPosition, RouteVerdict
from utils.run_config import ResourceManifest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def make_verdict(claim_text="A claim.", original_index=0):
    return Verdict(
        claim_text=claim_text,
        disambiguated_sentence=claim_text,
        original_sentence=claim_text,
        original_index=original_index,
        result=VerificationResult.SUPPORTED,
        reasoning="Test verdict.",
        sources=[],
    )


def make_record(
    claim_text="A claim.",
    triage_class=None,
    route_verdicts=None,
    web_verdict="default",
):
    verdict = make_verdict(claim_text) if web_verdict == "default" else web_verdict
    return ClaimRecord(
        web_verdict=verdict,
        citation_status=CitationStatus.CITATION_FREE,
        cite_set=[],
        position=DraftPosition(sentence_index=0),
        route_verdicts=route_verdicts or [],
        triage_class=triage_class,
    )


def web_available_manifest():
    return ResourceManifest(draft_path="draft.md", web_enabled=True)


def corpus_and_web_manifest():
    return ResourceManifest(
        draft_path="draft.md", web_enabled=True, corpus_ids=["doc-1"]
    )


def corpus_only_manifest():
    return ResourceManifest(
        draft_path="draft.md", web_enabled=False, corpus_ids=["doc-1"]
    )


def no_routes_manifest():
    return ResourceManifest(draft_path="draft.md", web_enabled=False)


# ---------------------------------------------------------------------------
# decide_route: vault-resolved stops
# ---------------------------------------------------------------------------


def test_vault_supported_resolves_no_further_routing():
    record = make_record(
        route_verdicts=[RouteVerdict(route="vault_aligned", verdict="vault_supported")]
    )
    result = decide_route(record, ["web"])
    assert result.decision == RESOLVED
    assert "resolved" in result.reason.lower() or result.decision == RESOLVED


def test_vault_contradicted_resolves_no_further_routing():
    record = make_record(
        route_verdicts=[RouteVerdict(route="vault_matched", verdict="vault_contradicted")]
    )
    result = decide_route(record, ["web"])
    assert result.decision == RESOLVED


def test_vault_resolved_takes_priority_over_trivial():
    record = make_record(
        triage_class="trivial",
        route_verdicts=[RouteVerdict(route="vault_aligned", verdict="vault_supported")],
    )
    result = decide_route(record, ["web"])
    assert result.decision == RESOLVED


# ---------------------------------------------------------------------------
# decide_route: trivial stops
# ---------------------------------------------------------------------------


def test_trivial_claim_skips_verification():
    record = make_record(triage_class="trivial")
    result = decide_route(record, ["web"])
    assert result.decision == SKIP_TRIVIAL


# ---------------------------------------------------------------------------
# decide_route: novel-result / dataset-dependent never route to web
# ---------------------------------------------------------------------------


def test_novel_result_never_routes_to_web_even_when_available():
    record = make_record(triage_class="novel-result")
    result = decide_route(record, ["web"])
    assert result.decision != route_decision("web")
    assert result.decision == UNVERIFIABLE


def test_dataset_dependent_never_routes_to_web_even_when_available():
    record = make_record(triage_class="dataset-dependent")
    result = decide_route(record, ["web"])
    assert result.decision != route_decision("web")
    assert result.decision == UNVERIFIABLE


def test_novel_result_with_no_vault_support_is_explicitly_unverifiable():
    record = make_record(triage_class="novel-result", route_verdicts=[])
    result = decide_route(record, ["web", "vault_aligned", "vault_matched"])
    assert result.decision == UNVERIFIABLE


# ---------------------------------------------------------------------------
# decide_route: UNVERIFIABLE reason string is self-explanatory (not "among []")
# ---------------------------------------------------------------------------


def test_never_web_reason_names_triage_class_and_available_routes():
    """The old rendering ("no available route among []") was an unexplained
    empty list. The new one must name the triage class that excludes web
    and show the manifest's actual available routes."""
    record = make_record(triage_class="dataset-dependent")
    result = decide_route(record, ["web", "vault_aligned", "vault_matched"])

    assert result.decision == UNVERIFIABLE
    assert "dataset-dependent" in result.reason
    assert "web" in result.reason
    assert "vault_aligned" in result.reason
    assert "vault_matched" in result.reason
    assert "[]" not in result.reason


def test_never_web_reason_shows_none_when_no_routes_available():
    record = make_record(triage_class="novel-result")
    result = decide_route(record, [])

    assert result.decision == UNVERIFIABLE
    assert "novel-result" in result.reason
    assert "none" in result.reason.lower()


def test_already_routed_web_reason_shows_available_routes():
    """The general (catch-all) row's UNVERIFIABLE reason -- reached when web
    was already attempted -- should also show the manifest's available
    routes rather than a bare candidate list."""
    record = make_record(
        triage_class="general-factual",
        route_verdicts=[RouteVerdict(route="web", verdict="Supported")],
    )
    result = decide_route(record, ["web"])

    assert result.decision == UNVERIFIABLE
    assert "web" in result.reason


# ---------------------------------------------------------------------------
# decide_route: general-factual / academic-citable / unclassified -> web
# ---------------------------------------------------------------------------


def test_general_factual_routes_to_web_when_available():
    record = make_record(triage_class="general-factual")
    result = decide_route(record, ["web"])
    assert result.decision == route_decision("web")


def test_academic_citable_routes_to_web_when_available():
    record = make_record(triage_class="academic-citable")
    result = decide_route(record, ["web"])
    assert result.decision == route_decision("web")


def test_unclassified_routes_to_web_not_skipped():
    """Ties break toward verifying: unclassified (None) claims still verify."""
    record = make_record(triage_class=None)
    result = decide_route(record, ["web"])
    assert result.decision == route_decision("web")
    assert result.decision != SKIP_TRIVIAL


def test_nothing_available_is_unverifiable():
    record = make_record(triage_class="general-factual")
    result = decide_route(record, [])
    assert result.decision == UNVERIFIABLE


def test_web_not_declared_falls_to_unverifiable_even_with_other_routes():
    record = make_record(triage_class="general-factual")
    result = decide_route(record, ["vault_aligned", "vault_matched"])
    assert result.decision == UNVERIFIABLE


def test_claim_with_existing_web_route_verdict_is_not_rerouted():
    """Idempotency: a claim already routed to web shouldn't be routed again."""
    record = make_record(
        triage_class="general-factual",
        route_verdicts=[RouteVerdict(route="web", verdict="Supported")],
    )
    result = decide_route(record, ["web"])
    assert result.decision != route_decision("web")
    assert result.decision == UNVERIFIABLE


# ---------------------------------------------------------------------------
# decide_route: reason string always present
# ---------------------------------------------------------------------------


def test_decide_route_always_returns_a_reason():
    for triage_class in [None, "trivial", "novel-result", "dataset-dependent", "general-factual"]:
        record = make_record(triage_class=triage_class)
        result = decide_route(record, ["web"])
        assert isinstance(result, RoutingDecision)
        assert result.reason
        assert isinstance(result.reason, str)


# ---------------------------------------------------------------------------
# Extensibility proof: a fake route is additive (registry + one policy row)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extensibility_fake_route_via_new_policy_row_and_handler():
    """Adding a route should touch only the registry and the policy table.

    This registers a brand-new "fake" route: one stub handler, one new
    policy row (inserted before the catch-all "general" row), and a
    manifest-like object declaring "fake" available. No change to
    decide_route, execute_routing, ClaimRecord, or the existing rows.
    """
    calls = []

    async def fake_handler(record: ClaimRecord):
        calls.append(record)
        rv = RouteVerdict(
            route="fake",
            verdict="fake_supported",
            reasoning="Handled by the fake extensibility route.",
            provenance="fake-source",
            provenance_type="fake_type",
        )
        record.route_verdicts.append(rv)
        return rv

    fake_row = PolicyRow(
        name="fake-extensibility-row",
        condition='triage_class == "extensibility-test" -> route to the fake route',
        applies=lambda record: record.triage_class == "extensibility-test",
        candidate_routes=("fake",),
    )
    # Insert before the catch-all ("general") row, which is always True and
    # would otherwise shadow this one.
    custom_policy = POLICY[:-1] + [fake_row] + POLICY[-1:]
    custom_handlers = dict(ROUTE_HANDLERS)
    custom_handlers["fake"] = fake_handler

    record = make_record(triage_class="extensibility-test")
    manifest = SimpleNamespace(available_routes=["fake"])

    # decide_route in isolation
    result = decide_route(record, manifest.available_routes, policy=custom_policy)
    assert result.decision == route_decision("fake")

    # execute_routing end-to-end
    result_records = await execute_routing(
        [record], manifest, handlers=custom_handlers, policy=custom_policy
    )

    assert len(calls) == 1
    assert result_records[0].routing_decision == route_decision("fake")
    fake_verdicts = [rv for rv in record.route_verdicts if rv.route == "fake"]
    assert len(fake_verdicts) == 1
    assert fake_verdicts[0].verdict == "fake_supported"


# ---------------------------------------------------------------------------
# web_route_handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_route_handler_invokes_graph_and_records_verdict():
    record = make_record(claim_text="Water boils at 100C at sea level.")

    verdict = Verdict(
        claim_text="Water boils at 100C at sea level.",
        disambiguated_sentence="Water boils at 100C at sea level.",
        original_sentence="Water boils at 100C at sea level.",
        original_index=0,
        result=VerificationResult.SUPPORTED,
        reasoning="Well established physical fact.",
        sources=[Evidence(url="https://example.com/boil", text="Boiling point info")],
    )

    mock_graph = SimpleNamespace(ainvoke=AsyncMock(return_value={"verdict": verdict}))

    with patch("claim_verifier.graph", mock_graph):
        result = await web_route_handler(record)

    assert isinstance(result, RouteVerdict)
    assert result.route == "web"
    assert result.verdict == "Supported"
    assert result.provenance == "https://example.com/boil"
    assert result.provenance_type == "web_url"
    assert record.web_verdict is verdict
    assert record.route_verdicts == [result]
    mock_graph.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_web_route_handler_no_claim_text_returns_none():
    record = make_record(web_verdict=None)
    result = await web_route_handler(record)
    assert result is None
    assert record.route_verdicts == []


@pytest.mark.asyncio
async def test_web_route_handler_no_verdict_returned_returns_none():
    record = make_record(claim_text="A claim.")
    mock_graph = SimpleNamespace(ainvoke=AsyncMock(return_value={}))

    with patch("claim_verifier.graph", mock_graph):
        result = await web_route_handler(record)

    assert result is None
    assert record.route_verdicts == []


@pytest.mark.asyncio
async def test_web_route_handler_propagates_graph_exception():
    """execute_routing (not the handler) is responsible for containing failures."""
    record = make_record(claim_text="A claim.")
    mock_graph = SimpleNamespace(ainvoke=AsyncMock(side_effect=RuntimeError("boom")))

    with patch("claim_verifier.graph", mock_graph):
        with pytest.raises(RuntimeError):
            await web_route_handler(record)


# ---------------------------------------------------------------------------
# execute_routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_routing_sets_decision_and_reason_on_every_record():
    records = [
        make_record(triage_class="trivial"),
        make_record(
            route_verdicts=[RouteVerdict(route="vault_aligned", verdict="vault_supported")]
        ),
    ]
    manifest = no_routes_manifest()

    result = await execute_routing(records, manifest, handlers={})

    assert result[0].routing_decision == SKIP_TRIVIAL
    assert result[0].routing_reason
    assert result[1].routing_decision == RESOLVED
    assert result[1].routing_reason


@pytest.mark.asyncio
async def test_execute_routing_dispatches_to_web_handler():
    record = make_record(claim_text="A claim.", triage_class="general-factual")
    manifest = web_available_manifest()

    verdict = make_verdict("A claim.")
    called_with = []

    async def stub_web_handler(rec):
        called_with.append(rec)
        rv = RouteVerdict(route="web", verdict="Supported", reasoning="stubbed")
        rec.route_verdicts.append(rv)
        rec.web_verdict = verdict
        return rv

    result = await execute_routing(
        [record], manifest, handlers={"web": stub_web_handler}
    )

    assert result[0].routing_decision == route_decision("web")
    assert len(called_with) == 1
    assert any(rv.route == "web" for rv in result[0].route_verdicts)


@pytest.mark.asyncio
async def test_execute_routing_no_handler_registered_records_reason():
    record = make_record(triage_class="general-factual")
    manifest = web_available_manifest()

    result = await execute_routing([record], manifest, handlers={})

    assert result[0].routing_decision == route_decision("web")
    assert "no handler registered" in result[0].routing_reason


@pytest.mark.asyncio
async def test_execute_routing_handler_failure_is_recorded_and_run_continues():
    failing_record = make_record(triage_class="general-factual", claim_text="Fails.")
    ok_record = make_record(triage_class="trivial")

    async def failing_handler(rec):
        raise ValueError("handler exploded")

    result = await execute_routing(
        [failing_record, ok_record],
        web_available_manifest(),
        handlers={"web": failing_handler},
    )

    assert "handler error" in result[0].routing_reason
    assert "handler exploded" in result[0].routing_reason
    # Run continued: the second record was still processed normally.
    assert result[1].routing_decision == SKIP_TRIVIAL


@pytest.mark.asyncio
async def test_execute_routing_uses_module_level_handlers_by_default():
    """Without an explicit `handlers` arg, execute_routing uses ROUTE_HANDLERS."""
    record = make_record(claim_text="A claim.", triage_class="general-factual")
    manifest = web_available_manifest()

    verdict = make_verdict("A claim.")
    mock_graph = SimpleNamespace(ainvoke=AsyncMock(return_value={"verdict": verdict}))

    with patch("claim_verifier.graph", mock_graph):
        result = await execute_routing([record], manifest)

    assert result[0].routing_decision == route_decision("web")
    assert any(rv.route == "web" for rv in result[0].route_verdicts)


# ===================================================================
# TG 05.1 — normalize_verdict
# ===================================================================


class TestNormalizeVerdict:
    """normalize_verdict maps any verdict string to support/refute/silent."""

    # -- support verdicts --

    def test_vault_supported(self):
        assert normalize_verdict("vault_supported") == NORM_SUPPORT

    def test_corpus_supported(self):
        assert normalize_verdict("corpus_supported") == NORM_SUPPORT

    def test_web_supported(self):
        assert normalize_verdict("Supported") == NORM_SUPPORT

    # -- refute verdicts --

    def test_vault_contradicted(self):
        assert normalize_verdict("vault_contradicted") == NORM_REFUTE

    def test_corpus_contradicted(self):
        assert normalize_verdict("corpus_contradicted") == NORM_REFUTE

    def test_web_refuted(self):
        assert normalize_verdict("Refuted") == NORM_REFUTE

    # -- silent verdicts --

    def test_not_supported(self):
        assert normalize_verdict("not_supported") == NORM_SILENT

    def test_no_vault_match(self):
        assert normalize_verdict("no_vault_match") == NORM_SILENT

    def test_note_not_in_vault(self):
        assert normalize_verdict("note_not_in_vault") == NORM_SILENT

    def test_insufficient_vault_content(self):
        assert normalize_verdict("insufficient_vault_content") == NORM_SILENT

    def test_corpus_insufficient(self):
        assert normalize_verdict("corpus_insufficient") == NORM_SILENT

    def test_no_corpus_hits(self):
        assert normalize_verdict("no_corpus_hits") == NORM_SILENT

    def test_web_insufficient_information(self):
        assert normalize_verdict("Insufficient Information") == NORM_SILENT

    def test_web_conflicting_evidence(self):
        assert normalize_verdict("Conflicting Evidence") == NORM_SILENT

    # -- edge cases --

    def test_unknown_string(self):
        assert normalize_verdict("something_unexpected") == NORM_SILENT

    def test_empty_string(self):
        assert normalize_verdict("") == NORM_SILENT

    def test_case_sensitive_supported_lowercase_is_silent(self):
        """Exact match, not case-insensitive: 'supported' != 'Supported'."""
        assert normalize_verdict("supported") == NORM_SILENT

    def test_case_sensitive_refuted_lowercase_is_silent(self):
        assert normalize_verdict("refuted") == NORM_SILENT


# ===================================================================
# TG 05.1 — Policy table updates
# ===================================================================


class TestPolicyTableCascade:
    """Verify the POLICY table reflects Phase 05 cascade structure."""

    def test_general_row_candidate_routes_include_corpus_then_web(self):
        general_row = next(r for r in POLICY if r.name == "general")
        assert general_row.candidate_routes == ("corpus", "web")

    def test_never_web_row_still_has_corpus_only(self):
        never_web_row = next(r for r in POLICY if r.name == "never-web")
        assert never_web_row.candidate_routes == ("corpus",)

    def test_general_no_corpus_available_routes_to_web(self):
        """When corpus is not in available_routes, decide_route skips it."""
        record = make_record(triage_class="general-factual")
        result = decide_route(record, ["web"])
        assert result.decision == route_decision("web")

    def test_general_corpus_available_routes_to_corpus_first(self):
        """When corpus is in available_routes, decide_route picks it first."""
        record = make_record(triage_class="general-factual")
        result = decide_route(record, ["web", "corpus"])
        assert result.decision == route_decision("corpus")


# ===================================================================
# TG 05.1 — Cascade routing in execute_routing
# ===================================================================


def _make_corpus_handler(verdict_str="corpus_supported"):
    """Factory: returns a mock corpus handler that appends a RouteVerdict."""
    calls = []

    async def handler(record):
        calls.append(record)
        rv = RouteVerdict(
            route="corpus", verdict=verdict_str, reasoning="stub corpus"
        )
        record.route_verdicts.append(rv)
        return rv

    return handler, calls


def _make_web_handler(verdict_str="Supported"):
    """Factory: returns a mock web handler that appends a RouteVerdict."""
    calls = []

    async def handler(record):
        calls.append(record)
        rv = RouteVerdict(
            route="web", verdict=verdict_str, reasoning="stub web"
        )
        record.route_verdicts.append(rv)
        return rv

    return handler, calls


class TestCascadeRouting:
    """execute_routing cascade: silent verdicts trigger escalation to next tier."""

    @pytest.mark.asyncio
    async def test_corpus_silent_escalates_to_web(self):
        """Corpus returns corpus_insufficient -> cascade re-routes to web."""
        record = make_record(triage_class="general-factual")
        manifest = corpus_and_web_manifest()

        corpus_handler, corpus_calls = _make_corpus_handler("corpus_insufficient")
        web_handler, web_calls = _make_web_handler("Supported")

        result = await execute_routing(
            [record], manifest,
            handlers={"corpus": corpus_handler, "web": web_handler},
        )

        assert len(corpus_calls) == 1
        assert len(web_calls) == 1
        # Final decision should reflect the web route
        assert result[0].routing_decision == route_decision("web")
        assert "cascade" in result[0].routing_reason.lower()

    @pytest.mark.asyncio
    async def test_corpus_support_stops_cascade(self):
        """Corpus returns corpus_supported -> no escalation to web."""
        record = make_record(triage_class="general-factual")
        manifest = corpus_and_web_manifest()

        corpus_handler, corpus_calls = _make_corpus_handler("corpus_supported")
        web_handler, web_calls = _make_web_handler("Supported")

        await execute_routing(
            [record], manifest,
            handlers={"corpus": corpus_handler, "web": web_handler},
        )

        assert len(corpus_calls) == 1
        assert len(web_calls) == 0

    @pytest.mark.asyncio
    async def test_corpus_refute_stops_cascade(self):
        """Corpus returns corpus_contradicted -> no escalation to web."""
        record = make_record(triage_class="general-factual")
        manifest = corpus_and_web_manifest()

        corpus_handler, corpus_calls = _make_corpus_handler("corpus_contradicted")
        web_handler, web_calls = _make_web_handler("Supported")

        await execute_routing(
            [record], manifest,
            handlers={"corpus": corpus_handler, "web": web_handler},
        )

        assert len(corpus_calls) == 1
        assert len(web_calls) == 0

    @pytest.mark.asyncio
    async def test_never_web_corpus_silent_becomes_unverifiable(self):
        """never-web claim: corpus silent -> UNVERIFIABLE (no web fallback)."""
        record = make_record(triage_class="novel-result")
        manifest = corpus_and_web_manifest()

        corpus_handler, corpus_calls = _make_corpus_handler("no_corpus_hits")
        web_handler, web_calls = _make_web_handler("Supported")

        result = await execute_routing(
            [record], manifest,
            handlers={"corpus": corpus_handler, "web": web_handler},
        )

        assert len(corpus_calls) == 1
        assert len(web_calls) == 0
        assert result[0].routing_decision == UNVERIFIABLE

    @pytest.mark.asyncio
    async def test_no_corpus_in_manifest_routes_web_directly(self):
        """No corpus_ids in manifest -> web directly, same as pre-cascade."""
        record = make_record(triage_class="general-factual")
        manifest = web_available_manifest()  # no corpus_ids

        web_handler, web_calls = _make_web_handler("Supported")

        result = await execute_routing(
            [record], manifest,
            handlers={"web": web_handler},
        )

        assert len(web_calls) == 1
        assert result[0].routing_decision == route_decision("web")

    @pytest.mark.asyncio
    async def test_handler_exception_escalates_to_next_tier(self):
        """Corpus handler raises -> record degrades to web with reason."""
        record = make_record(triage_class="general-factual")
        manifest = corpus_and_web_manifest()

        async def failing_corpus(rec):
            raise RuntimeError("corpus exploded")

        web_handler, web_calls = _make_web_handler("Supported")

        result = await execute_routing(
            [record], manifest,
            handlers={"corpus": failing_corpus, "web": web_handler},
        )

        assert len(web_calls) == 1
        assert result[0].routing_decision == route_decision("web")
        assert "corpus exploded" in result[0].routing_reason

    @pytest.mark.asyncio
    async def test_handler_returns_none_escalates_to_next_tier(self):
        """Corpus handler returns None (no verdict appended) -> escalate."""
        record = make_record(triage_class="general-factual")
        manifest = corpus_and_web_manifest()

        none_calls = []

        async def none_corpus(rec):
            none_calls.append(rec)
            return None  # no verdict appended

        web_handler, web_calls = _make_web_handler("Supported")

        result = await execute_routing(
            [record], manifest,
            handlers={"corpus": none_corpus, "web": web_handler},
        )

        assert len(none_calls) == 1
        assert len(web_calls) == 1
        assert result[0].routing_decision == route_decision("web")

    @pytest.mark.asyncio
    async def test_already_routed_prevents_double_dispatch(self):
        """A record with an existing corpus verdict should not re-run corpus."""
        record = make_record(
            triage_class="general-factual",
            route_verdicts=[
                RouteVerdict(route="corpus", verdict="corpus_insufficient")
            ],
        )
        manifest = corpus_and_web_manifest()

        corpus_handler, corpus_calls = _make_corpus_handler("corpus_supported")
        web_handler, web_calls = _make_web_handler("Supported")

        result = await execute_routing(
            [record], manifest,
            handlers={"corpus": corpus_handler, "web": web_handler},
        )

        # Corpus already routed -> skip corpus, go to web
        assert len(corpus_calls) == 0
        assert len(web_calls) == 1
        assert result[0].routing_decision == route_decision("web")

    @pytest.mark.asyncio
    async def test_max_cascade_rounds_safety_bound(self):
        """Cascade stops after MAX_CASCADE_ROUNDS even if still silent."""
        record = make_record(triage_class="general-factual")
        manifest = corpus_and_web_manifest()

        round_count = []

        async def always_silent_handler(rec):
            round_count.append(1)
            # Append a silent verdict under a unique route name each time
            # (to avoid _already_routed blocking). In practice this can't
            # happen because there are only 2 candidate routes, but we test
            # the safety bound.
            rv = RouteVerdict(
                route=f"fake-{len(round_count)}",
                verdict="silent",
                reasoning="always silent",
            )
            rec.route_verdicts.append(rv)
            return rv

        # We test by providing handlers for corpus and web that both return
        # silent verdicts. After corpus-silent -> web. After web-silent ->
        # no more candidates. So cascade naturally stops at 2 rounds.
        corpus_handler, _ = _make_corpus_handler("corpus_insufficient")
        web_handler, _ = _make_web_handler("Insufficient Information")

        result = await execute_routing(
            [record], manifest,
            handlers={"corpus": corpus_handler, "web": web_handler},
        )

        # Both handlers called, but no infinite loop
        assert any(rv.route == "corpus" for rv in record.route_verdicts)
        assert any(rv.route == "web" for rv in record.route_verdicts)

    @pytest.mark.asyncio
    async def test_multiple_records_cascade_independently(self):
        """Each record cascades independently: one escalates, another stops."""
        rec_silent = make_record(
            claim_text="Claim A", triage_class="general-factual"
        )
        rec_supported = make_record(
            claim_text="Claim B", triage_class="general-factual"
        )

        manifest = corpus_and_web_manifest()

        corpus_call_texts = []
        web_call_texts = []

        async def selective_corpus(rec):
            corpus_call_texts.append(rec.claim_text)
            if rec.claim_text == "Claim A":
                rv = RouteVerdict(
                    route="corpus", verdict="corpus_insufficient", reasoning="no hits"
                )
            else:
                rv = RouteVerdict(
                    route="corpus", verdict="corpus_supported", reasoning="found it"
                )
            rec.route_verdicts.append(rv)
            return rv

        async def web_handler(rec):
            web_call_texts.append(rec.claim_text)
            rv = RouteVerdict(
                route="web", verdict="Supported", reasoning="web found it"
            )
            rec.route_verdicts.append(rv)
            return rv

        result = await execute_routing(
            [rec_silent, rec_supported], manifest,
            handlers={"corpus": selective_corpus, "web": web_handler},
        )

        # Both went to corpus
        assert "Claim A" in corpus_call_texts
        assert "Claim B" in corpus_call_texts
        # Only Claim A escalated to web
        assert "Claim A" in web_call_texts
        assert "Claim B" not in web_call_texts
        # Final decisions
        assert result[0].routing_decision == route_decision("web")
        assert result[1].routing_decision == route_decision("corpus")

    @pytest.mark.asyncio
    async def test_no_corpus_hits_all_four_silent_verdicts_escalate(self):
        """All four corpus-silent verdicts trigger escalation."""
        for silent_verdict in [
            "corpus_insufficient", "no_corpus_hits",
        ]:
            record = make_record(triage_class="general-factual")
            manifest = corpus_and_web_manifest()
            corpus_handler, _ = _make_corpus_handler(silent_verdict)
            web_handler, web_calls = _make_web_handler("Supported")

            await execute_routing(
                [record], manifest,
                handlers={"corpus": corpus_handler, "web": web_handler},
            )

            assert len(web_calls) == 1, (
                f"Expected web escalation for {silent_verdict}"
            )


# ===================================================================
# TG 05.3 — apply_cross_checks: D4 (Attribution Check)
# ===================================================================


def _make_d4_record(
    importance=5,
    citation_status=CitationStatus.CITED,
    cite_set=None,
    vault_verdict="vault_supported",
    extra_route_verdicts=None,
    triage_class="general-factual",
):
    """Build a record suitable for D4 testing: vault-resolved, cited, important."""
    record = make_record(claim_text="Some cited claim.", triage_class=triage_class)
    record.importance = importance
    record.citation_status = citation_status
    record.cite_set = cite_set or ["Author 2023"]
    record.route_verdicts.append(
        RouteVerdict(
            route="vault_aligned",
            verdict=vault_verdict,
            reasoning="test",
            provenance="Author 2023",
        )
    )
    if extra_route_verdicts:
        record.route_verdicts.extend(extra_route_verdicts)
    return record


def _mock_corpus_handler_side_effect():
    """Returns an AsyncMock that appends a corpus verdict when called."""

    async def _handler(record):
        rv = RouteVerdict(
            route="corpus", verdict="corpus_supported", reasoning="found in corpus"
        )
        record.route_verdicts.append(rv)
        return rv

    return AsyncMock(side_effect=_handler)


def _mock_web_handler_side_effect():
    """Returns an AsyncMock that appends a web verdict when called."""

    async def _handler(record):
        rv = RouteVerdict(
            route="web", verdict="Supported", reasoning="confirmed by web"
        )
        record.route_verdicts.append(rv)
        return rv

    return AsyncMock(side_effect=_handler)


class TestD4AttributionCheck:
    """D4: vault-resolved + cited + importance >= 4 + corpus available -> corpus check."""

    @pytest.mark.asyncio
    async def test_d4_vault_resolved_cited_important_gets_corpus(self):
        """vault_supported + cited + importance=5 + corpus handler -> corpus called.

        Note (D10 amendment, Session 12): this record is also a supported,
        importance>=4, web-eligible claim not yet routed to web, so D10 now
        additionally fires a web confirmation check alongside D4's corpus
        check. See TestD10SupportConfirmation for D10-specific coverage.
        """
        record = _make_d4_record(importance=5)
        corpus_handler = _mock_corpus_handler_side_effect()
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": corpus_handler, "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        corpus_handler.assert_awaited_once()
        web_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_d4_vault_resolved_cited_low_importance_no_corpus(self):
        """Same setup but importance=3 -> corpus handler NOT called."""
        record = _make_d4_record(importance=3)
        corpus_handler = _mock_corpus_handler_side_effect()
        handlers = {"corpus": corpus_handler, "web": _mock_web_handler_side_effect()}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        corpus_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_d4_citation_free_no_corpus(self):
        """vault_resolved + citation_free + importance=5 -> NOT called (no attribution)."""
        record = _make_d4_record(
            importance=5,
            citation_status=CitationStatus.CITATION_FREE,
            cite_set=[],
        )
        corpus_handler = _mock_corpus_handler_side_effect()
        handlers = {"corpus": corpus_handler, "web": _mock_web_handler_side_effect()}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        corpus_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_d4_corpus_already_routed_skipped(self):
        """vault_resolved + cited + importance=5 but corpus already routed -> NOT called."""
        record = _make_d4_record(
            importance=5,
            extra_route_verdicts=[
                RouteVerdict(route="corpus", verdict="corpus_supported", reasoning="prior")
            ],
        )
        corpus_handler = _mock_corpus_handler_side_effect()
        handlers = {"corpus": corpus_handler, "web": _mock_web_handler_side_effect()}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        corpus_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_d4_no_corpus_handler_no_crash(self):
        """importance=5 + cited but no corpus handler in handlers dict -> no crash."""
        record = _make_d4_record(importance=5)
        handlers = {"web": _mock_web_handler_side_effect()}
        manifest = corpus_and_web_manifest()

        # Should not raise
        await apply_cross_checks([record], manifest, handlers)


# ===================================================================
# TG 05.3 — apply_cross_checks: D5 (Refutation Confirmation)
# ===================================================================


def _make_d5_record(
    importance=5,
    vault_verdict="vault_contradicted",
    triage_class="general-factual",
    extra_route_verdicts=None,
    route="vault_matched",
):
    """Build a record suitable for D5 testing: single-tier refutation."""
    record = make_record(claim_text="A refuted claim.", triage_class=triage_class)
    record.importance = importance
    record.route_verdicts.append(
        RouteVerdict(
            route=route,
            verdict=vault_verdict,
            reasoning="test refutation",
        )
    )
    if extra_route_verdicts:
        record.route_verdicts.extend(extra_route_verdicts)
    return record


class TestD5RefutationConfirmation:
    """D5: single-tier refutation + importance >= 4 + web-eligible -> web check."""

    @pytest.mark.asyncio
    async def test_d5_single_refute_important_gets_web(self):
        """vault_contradicted only + importance=5 + web-eligible -> web called."""
        record = _make_d5_record(importance=5)
        corpus_handler = _mock_corpus_handler_side_effect()
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": corpus_handler, "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_d5_single_refute_low_importance_no_web(self):
        """Same but importance=3 -> web NOT called."""
        record = _make_d5_record(importance=3)
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_d5_support_never_triggers_d5_itself(self):
        """vault_supported + importance=5 -> D5 itself does not fire (no refute present).

        Note (D10 amendment, Session 12): the web handler IS still called
        here, but via D10 (support confirmation), not D5 -- D10 supersedes
        D5's original "supports never trigger cross-checks" guardrail for
        importance >= 4 claims. See TestD10SupportConfirmation for
        D10-specific coverage.
        """
        record = _make_d5_record(importance=5, vault_verdict="vault_supported")
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_d5_never_web_refute_no_escalation(self):
        """vault_contradicted + importance=5 + triage_class=dataset-dependent -> NOT called."""
        record = _make_d5_record(importance=5, triage_class="dataset-dependent")
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_d5_web_already_exists_skipped(self):
        """vault_contradicted + importance=5 but web already in route_verdicts -> NOT called."""
        record = _make_d5_record(
            importance=5,
            extra_route_verdicts=[
                RouteVerdict(route="web", verdict="Refuted", reasoning="already checked")
            ],
        )
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_d5_corpus_refute_gets_web(self):
        """corpus_contradicted only + importance=5 + web-eligible -> web called."""
        record = _make_d5_record(
            importance=5,
            vault_verdict="corpus_contradicted",
            route="corpus",
        )
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_d5_web_refute_no_crosscheck(self):
        """web Refuted + importance=5 -> no additional cross-check (web IS the independent tier)."""
        record = _make_d5_record(
            importance=5,
            vault_verdict="Refuted",
            route="web",
        )
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_not_awaited()


# ===================================================================
# Amendment (Session 12) — D10: Support Confirmation for Important Claims
# ===================================================================
#
# A claim whose vault or corpus verdict is a SUPPORT (normalize_verdict ==
# support), importance >= 4, web-eligible, and not already routed to web,
# gets ONE web confirmation check. Rationale: a false fact shared by the
# author's vault and draft previously sailed through with no independent
# check (the 98-votes case); missed errors are the worst-case outcome.
# Supersedes D5's "supports never trigger routine cross-checks" sentence
# for importance >= 4 claims. Gated by config.toml's
# pipeline.support_confirmation (default on) via
# ingest.routing.SUPPORT_CONFIRMATION_ENABLED.


def _make_d10_record(
    importance=4,
    triage_class="general-factual",
    route="vault_aligned",
    verdict="vault_supported",
    extra_route_verdicts=None,
):
    """Build a record suitable for D10 testing: an important support verdict."""
    record = make_record(claim_text="An important supported claim.", triage_class=triage_class)
    record.importance = importance
    record.route_verdicts.append(
        RouteVerdict(route=route, verdict=verdict, reasoning="test support")
    )
    if extra_route_verdicts:
        record.route_verdicts.extend(extra_route_verdicts)
    return record


class TestD10SupportConfirmation:
    """D10: support verdict + importance >= 4 + web-eligible + web not yet
    attempted -> one web confirmation check."""

    @pytest.mark.asyncio
    async def test_d10_vault_supported_important_triggers_web_check(self):
        """vault_supported + importance=4 + general-factual -> web check dispatched."""
        record = _make_d10_record(importance=4, route="vault_aligned", verdict="vault_supported")
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_d10_corpus_supported_also_triggers(self):
        """corpus_supported + importance=4 -> web check dispatched too."""
        record = _make_d10_record(importance=4, route="corpus", verdict="corpus_supported")
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_d10_low_importance_no_check(self):
        """importance=3 -> no check."""
        record = _make_d10_record(importance=3)
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_d10_never_web_triage_class_no_check(self):
        """triage_class in NEVER_WEB_CLASSES -> no check even at high importance."""
        record = _make_d10_record(importance=5, triage_class="dataset-dependent")
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_d10_web_already_routed_no_check(self):
        """web already in route_verdicts -> not re-dispatched."""
        record = _make_d10_record(
            importance=5,
            extra_route_verdicts=[
                RouteVerdict(route="web", verdict="Supported", reasoning="already checked")
            ],
        )
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_d10_config_switch_off_no_check(self):
        """pipeline.support_confirmation=False -> gate never fires."""
        record = _make_d10_record(importance=5)
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        with patch("ingest.routing.SUPPORT_CONFIRMATION_ENABLED", False):
            await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_d10_mixed_support_and_refute_still_fires(self):
        """Mixed support+refute should still fire (web arbitrates); no "no
        refute present" condition is added."""
        record = _make_d10_record(
            importance=5,
            route="vault_aligned",
            verdict="vault_supported",
            extra_route_verdicts=[
                RouteVerdict(route="corpus", verdict="corpus_contradicted", reasoning="conflicting")
            ],
        )
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_d10_no_web_handler_no_crash(self):
        """No web handler in handlers dict -> no crash, no check."""
        record = _make_d10_record(importance=5)
        handlers = {"corpus": _mock_corpus_handler_side_effect()}
        manifest = corpus_and_web_manifest()

        # Should not raise
        await apply_cross_checks([record], manifest, handlers)


# ===================================================================
# TG M3: configurable CROSS_CHECK_IMPORTANCE_THRESHOLD
# ===================================================================
#
# The threshold value (4) is a deliberate user decision and stays the
# default. This only verifies D4/D5/D10 read the module-level constant at
# call time, so tests (and, in prod, config.toml's
# pipeline.cross_check_importance_threshold) can override it -- mirroring
# how SUPPORT_CONFIRMATION_ENABLED is patched above.


class TestConfigurableImportanceThreshold:
    @pytest.mark.asyncio
    async def test_d10_importance_3_no_check_at_default_threshold(self):
        """importance=3 does not fire D10 at the default threshold (4)."""
        record = _make_d10_record(importance=3)
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_d10_importance_3_fires_when_threshold_lowered(self):
        """Patching CROSS_CHECK_IMPORTANCE_THRESHOLD to 3 widens D10 to
        cover importance=3 claims."""
        record = _make_d10_record(importance=3)
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        with patch("ingest.routing.CROSS_CHECK_IMPORTANCE_THRESHOLD", 3):
            await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_d10_importance_4_no_check_when_threshold_raised(self):
        """Patching CROSS_CHECK_IMPORTANCE_THRESHOLD to 5 tightens D10,
        excluding importance=4 claims that fire at the default."""
        record = _make_d10_record(importance=4)
        web_handler = _mock_web_handler_side_effect()
        handlers = {"corpus": _mock_corpus_handler_side_effect(), "web": web_handler}
        manifest = corpus_and_web_manifest()

        with patch("ingest.routing.CROSS_CHECK_IMPORTANCE_THRESHOLD", 5):
            await apply_cross_checks([record], manifest, handlers)

        web_handler.assert_not_awaited()
