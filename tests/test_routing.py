"""Tests for routing policy and route-handler registry (TG 03.2).

``decide_route`` is a pure, deterministic function (no LLM, no I/O, no
graph import) that decides what happens to a claim after vault
verification + triage. ``execute_routing`` applies it across a batch of
records and dispatches to registered route handlers.

See ingest/routing.py.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from claim_verifier.schemas import Evidence, Verdict, VerificationResult
from ingest.routing import (
    POLICY,
    RESOLVED,
    ROUTE_HANDLERS,
    SKIP_TRIVIAL,
    UNVERIFIABLE,
    PolicyRow,
    RoutingDecision,
    decide_route,
    execute_routing,
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
