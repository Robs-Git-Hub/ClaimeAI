"""Routing policy and route-handler registry (TG 03.2).

Vault verification (Phase 02) always runs and never gates on triage. Once
it and triage (TG 03.1, `ingest/triage.py`) have populated a `ClaimRecord`,
every claim needs one more decision: is it already resolved, does it need
no further verification at all, or should it be routed to a verification
route -- and if so, which one?

``decide_route`` is that decision, made purely: no LLM call, no I/O, no
network, no import of the verification graphs. It consults the
module-level ``POLICY`` table below -- a plain, ordered list of
``PolicyRow``s (first match wins) -- so the policy itself stays readable
and reviewable by the user, not buried in branching logic.

Design pillar 3 (see project-management/phase-plans/phase-03-triage-and-routing.md):
the router is an extension point. Adding a new route (corpus RAG in
Phase 04, a specialist DB search later) is meant to touch only two
things:
    1. ``ROUTE_HANDLERS`` -- register the new handler under its route name.
    2. ``POLICY`` -- add the route name to the ``candidate_routes`` of
       whichever row(s) should be allowed to use it (or add a new row).
Nothing here, the orchestrator, the report, or the ``ClaimRecord`` schema
should need to change beyond that.

See docs/playbook/claim-record-design.md (Routing Decisions section,
appended for TG 03.2) for the vocabulary this module produces.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field

from utils.claim_record import CitationStatus, ClaimRecord, RouteVerdict, VaultVerdict
from utils.config import config as _config
from utils.run_config import ResourceManifest

logger = logging.getLogger(__name__)

_PIPELINE_CONFIG = _config.get("pipeline", {})

# Off = D10 (support confirmation) never fires, restoring pre-amendment
# behavior where supports never trigger routine cross-checks.
SUPPORT_CONFIRMATION_ENABLED: bool = _PIPELINE_CONFIG.get("support_confirmation", True)

# Bounds how many route handlers (each a network-bound call -- the web
# handler alone makes ~5 API calls per claim) run concurrently. A module-level
# implementation detail, not a user-facing knob (see TG 03.5).
MAX_CONCURRENT_ROUTES = 5

# ---------------------------------------------------------------------------
# Routing decision vocabulary
# ---------------------------------------------------------------------------

RESOLVED = "resolved"
SKIP_TRIVIAL = "skip-trivial"
UNVERIFIABLE = "unverifiable-by-available-routes"

# ---------------------------------------------------------------------------
# Normalized verdict vocabulary (TG 05.1)
# ---------------------------------------------------------------------------

NORM_SUPPORT = "support"
NORM_REFUTE = "refute"
NORM_SILENT = "silent"

_VERDICT_MAP: Dict[str, str] = {
    # Vault verdicts
    "vault_supported": NORM_SUPPORT,
    "vault_contradicted": NORM_REFUTE,
    "not_supported": NORM_SILENT,
    "no_vault_match": NORM_SILENT,
    "note_not_in_vault": NORM_SILENT,
    "insufficient_vault_content": NORM_SILENT,
    # Corpus verdicts
    "corpus_supported": NORM_SUPPORT,
    "corpus_contradicted": NORM_REFUTE,
    "corpus_insufficient": NORM_SILENT,
    "no_corpus_hits": NORM_SILENT,
    # Web verdicts (VerificationResult values)
    "Supported": NORM_SUPPORT,
    "Refuted": NORM_REFUTE,
    "Insufficient Information": NORM_SILENT,
    "Conflicting Evidence": NORM_SILENT,
    # Synthetic (cascade infrastructure)
    "handler_error": NORM_SILENT,
}


def normalize_verdict(verdict: str) -> str:
    """Normalize a route verdict to 'support', 'refute', or 'silent'.

    Used by cascade logic (escalate on silent) and conflict detection (TG 05.4).
    Unknown/unrecognized values map to 'silent' (never crash).
    """
    return _VERDICT_MAP.get(verdict, NORM_SILENT)


def _is_cascade_silent(verdict: str) -> bool:
    """Whether a verdict should trigger cascade escalation.

    Only verdicts *explicitly mapped* to ``NORM_SILENT`` trigger cascade.
    Unknown/extension-route verdicts (not in ``_VERDICT_MAP``) are treated
    as decisive -- the handler returned a result we simply don't categorize,
    and escalating would break extensibility (a custom route's custom verdict
    would wrongly cascade).
    """
    return _VERDICT_MAP.get(verdict) == NORM_SILENT


def route_decision(route: str) -> str:
    """The decision value meaning "route this claim to `route`"."""
    return f"route-{route}"


def route_name_from_decision(decision: str) -> Optional[str]:
    """Extract the route name from a "route-<name>" decision, else None."""
    prefix = "route-"
    if decision.startswith(prefix):
        return decision[len(prefix):]
    return None


class RoutingDecision(BaseModel):
    """The result of `decide_route`: what to do, and why."""

    decision: str = Field(
        description='One of RESOLVED, SKIP_TRIVIAL, UNVERIFIABLE, or "route-<name>"'
    )
    reason: str = Field(description="Human-readable explanation, for the audit trail")


# ---------------------------------------------------------------------------
# Policy table
# ---------------------------------------------------------------------------
#
# Evaluated top to bottom; the first row whose `applies(record)` is True
# wins. Rows with a `fixed_decision` resolve immediately (no routing).
# Rows with `candidate_routes` try each declared route in order, picking
# the first one that is both available (per the manifest) and not
# already recorded for this claim; if none qualify, the claim is marked
# `unverifiable-by-available-routes`.
#
# This table is meant to be read by a human reviewing the policy, not
# just by decide_route -- keep rows self-describing.


def _is_vault_resolved(record: ClaimRecord) -> bool:
    return any(
        rv.verdict in (VaultVerdict.VAULT_SUPPORTED.value, VaultVerdict.VAULT_CONTRADICTED.value)
        for rv in record.route_verdicts
    )


def _is_trivial(record: ClaimRecord) -> bool:
    return record.triage_class == "trivial"


NEVER_WEB_CLASSES = frozenset({"novel-result", "dataset-dependent"})


def _is_never_web(record: ClaimRecord) -> bool:
    return record.triage_class in NEVER_WEB_CLASSES


def _catch_all(record: ClaimRecord) -> bool:
    return True


@dataclass(frozen=True)
class PolicyRow:
    """One row of the routing policy table.

    `applies` decides whether this row governs a given record; the first
    matching row (in `POLICY` order) wins. `fixed_decision` short-circuits
    to a decision that doesn't depend on route availability (resolved,
    skip-trivial). `candidate_routes` is tried in order for rows that do
    route somewhere -- a route is used only if it's both declared in the
    manifest's `available_routes` and not already recorded on the claim.
    """

    name: str
    condition: str
    applies: Callable[[ClaimRecord], bool]
    candidate_routes: tuple = ()
    fixed_decision: Optional[str] = None


POLICY: List[PolicyRow] = [
    PolicyRow(
        name="vault-resolved",
        condition=(
            "Claim already has a vault verdict of vault_supported or "
            "vault_contradicted -> no further routing."
        ),
        applies=_is_vault_resolved,
        fixed_decision=RESOLVED,
    ),
    PolicyRow(
        name="trivial",
        condition='triage_class == "trivial" -> no verification needed.',
        applies=_is_trivial,
        fixed_decision=SKIP_TRIVIAL,
    ),
    PolicyRow(
        name="never-web",
        condition=(
            'triage_class in {"novel-result", "dataset-dependent"} -> NEVER route to '
            "web, regardless of anything else. Routed to 'corpus' (TG 04.3, "
            "ingest/corpus_route.py) when the manifest declares corpus_ids; "
            "otherwise falls to unverifiable-by-available-routes."
        ),
        applies=_is_never_web,
        candidate_routes=("corpus",),
    ),
    PolicyRow(
        name="general",
        condition=(
            "Otherwise (general-factual, academic-citable, or unclassified/None -- "
            "ties break toward verifying, never toward skipping) -> try corpus "
            "first (when declared), then web if corpus is silent or unavailable."
        ),
        applies=_catch_all,
        candidate_routes=("corpus", "web"),
    ),
]


def _already_routed(record: ClaimRecord, route: str) -> bool:
    """Whether `route` has already produced a recorded verdict for this claim."""
    return any(rv.route == route for rv in record.route_verdicts)


def _unverifiable_reason(
    row: PolicyRow, record: ClaimRecord, available_routes: List[str]
) -> str:
    """Render a self-explanatory UNVERIFIABLE reason.

    The naive rendering ("no available route among []") reads as a bug when
    a row's `candidate_routes` is empty by design (originally true of the
    "never-web" row, before Phase 04 added `candidate_routes=("corpus",)` to
    it). Instead of showing an empty post-exclusion list, name the route(s)
    being excluded and show the manifest's actual available routes, so the
    message explains *why* on its own.

    Both branches (empty and non-empty `candidate_routes`) name the record's
    `triage_class` -- TG 04.3 added `candidate_routes=("corpus",)` to the
    never-web row, which moved that row from the empty branch to the
    non-empty one; the triage class is included in both so a claim's
    excluded-from-web reason keeps naming *why* regardless of which branch
    renders it.
    """
    available_display = ", ".join(available_routes) if available_routes else "none"

    if not row.candidate_routes:
        return (
            f"{row.name}: triage class '{record.triage_class}' excludes web; "
            "no other available route can verify this claim "
            f"(available: {available_display})"
        )

    candidates_display = ", ".join(row.candidate_routes)
    return (
        f"{row.name}: triage class '{record.triage_class}' excludes web; "
        f"candidate route(s) {candidates_display} unavailable or already "
        "attempted; no other available route can verify this claim "
        f"(available: {available_display})"
    )


def decide_route(
    record: ClaimRecord,
    available_routes: List[str],
    policy: Optional[List[PolicyRow]] = None,
) -> RoutingDecision:
    """Decide what should happen to `record` next.

    Pure and deterministic: no LLM call, no I/O, no import of any
    verification graph. Walks `policy` (defaults to the module-level
    `POLICY`) in order and returns the first matching row's outcome.
    """
    rows = policy if policy is not None else POLICY

    for row in rows:
        if not row.applies(record):
            continue

        if row.fixed_decision is not None:
            return RoutingDecision(
                decision=row.fixed_decision, reason=f"{row.name}: {row.condition}"
            )

        for route in row.candidate_routes:
            if route in available_routes and not _already_routed(record, route):
                return RoutingDecision(
                    decision=route_decision(route),
                    reason=f"{row.name}: routed to '{route}'",
                )

        return RoutingDecision(
            decision=UNVERIFIABLE,
            reason=_unverifiable_reason(row, record, available_routes),
        )

    # Unreachable while POLICY's last row is a catch-all; kept as a safety net
    # for a caller-supplied `policy` that omits one.
    return RoutingDecision(decision=UNVERIFIABLE, reason="no policy rule matched")


# ---------------------------------------------------------------------------
# Route-handler protocol + registry
# ---------------------------------------------------------------------------


class RouteHandler(Protocol):
    """A route handler: claim record in, RouteVerdict out (or None)."""

    def __call__(self, record: ClaimRecord) -> Awaitable[Optional[RouteVerdict]]: ...


ROUTE_HANDLERS: Dict[str, RouteHandler] = {}


def _build_validated_claim(record: ClaimRecord):
    """Get the `ValidatedClaim` to feed the web route.

    Prefers `record.claim` (the identity carrier populated by the heavy
    pipeline's binder straight from extraction). Falls back to reconstructing
    one from `record.web_verdict`'s identity fields for Phase 01/02-style
    records where the verdict carried identity — `Verdict`
    (`claim_verifier.schemas`) duplicates `ValidatedClaim`'s identity fields
    (claim_text, disambiguated_sentence, original_sentence, original_index).
    `is_complete_declarative` is set True: a claim only reaches `ClaimRecord`
    after passing that check during extraction. Returns None if there's no
    usable claim text on either.
    """
    from claim_extractor.schemas import ValidatedClaim

    if record.claim is not None and record.claim.claim_text and record.claim.claim_text.strip():
        return record.claim

    verdict = record.web_verdict
    if verdict is None or not verdict.claim_text or not verdict.claim_text.strip():
        return None

    return ValidatedClaim(
        claim_text=verdict.claim_text,
        is_complete_declarative=True,
        disambiguated_sentence=verdict.disambiguated_sentence,
        original_sentence=verdict.original_sentence,
        original_index=verdict.original_index,
    )


async def web_route_handler(record: ClaimRecord) -> Optional[RouteVerdict]:
    """Verify one claim via the existing `claim_verifier` graph.

    Builds a `ValidatedClaim` from the record (see `_build_validated_claim`),
    invokes `claim_verifier.graph.ainvoke({"claim": claim})`, and records
    the outcome as a `RouteVerdict` (route="web") appended to
    `record.route_verdicts` -- the same route-generic list the vault
    routes use (`RouteVerdict.route` was always documented to include
    "web" as an example value; this list is per-route, not vault-only).
    Also updates `record.web_verdict` to the real result so
    `assign_suggested_actions` (Phase 02, unmodified) keeps working.

    The `claim_verifier` graph is imported lazily, inside this function,
    so importing `ingest.routing` doesn't drag in the full verification
    pipeline (LLM clients, search providers) -- only a run that actually
    routes a claim to web pays that import cost.

    Returns None if the record has no usable claim text or the graph
    produced no verdict. Exceptions from the graph call are NOT caught
    here -- they propagate to the caller (`execute_routing`), which is
    the single place responsible for turning a handler failure into a
    recorded reason rather than aborting the run.
    """
    claim = _build_validated_claim(record)
    if claim is None:
        logger.warning("web_route_handler: no usable claim text on record; skipping")
        return None

    from claim_verifier import graph as claim_verifier_graph

    result = await claim_verifier_graph.ainvoke({"claim": claim})
    verdict = result.get("verdict") if result else None
    if verdict is None:
        logger.warning("web_route_handler: no verdict returned for '%s'", claim.claim_text)
        return None

    record.web_verdict = verdict
    provenance = ", ".join(source.url for source in verdict.sources if source.url) or None
    route_verdict = RouteVerdict(
        route="web",
        verdict=verdict.result.value,
        reasoning=verdict.reasoning,
        provenance=provenance,
        provenance_type="web_url" if provenance else None,
    )
    record.route_verdicts.append(route_verdict)
    return route_verdict


ROUTE_HANDLERS["web"] = web_route_handler


# ---------------------------------------------------------------------------
# execute_routing
# ---------------------------------------------------------------------------


MAX_CASCADE_ROUNDS = 3


async def execute_routing(
    records: List[ClaimRecord],
    manifest: ResourceManifest,
    handlers: Optional[Dict[str, RouteHandler]] = None,
    policy: Optional[List[PolicyRow]] = None,
) -> List[ClaimRecord]:
    """Apply `decide_route` to every record and dispatch to registered handlers.

    Sets `routing_decision` and `routing_reason` on every record (audit
    trail). For a "route-<name>" decision, looks up `<name>` in `handlers`
    (defaults to the module-level `ROUTE_HANDLERS`) and awaits it. A route
    with no registered handler, or a handler that raises, is folded into
    `routing_reason` rather than aborting the batch -- one claim's failure
    must not stop the run. Modifies and returns `records` in place.

    **Cascade (TG 05.1):** After each concurrent dispatch round, records
    whose handler returned a *silent* verdict (or no verdict / exception)
    are re-routed via ``decide_route``. Because ``_already_routed`` checks
    existing ``route_verdicts``, the just-attempted route is skipped and
    the next candidate is selected automatically. The cascade repeats for
    up to ``MAX_CASCADE_ROUNDS`` rounds (safety bound).
    """
    active_handlers = handlers if handlers is not None else ROUTE_HANDLERS
    available_routes = manifest.available_routes

    # Phase 1: initial routing decisions for ALL records
    for record in records:
        result = decide_route(record, available_routes, policy=policy)
        record.routing_decision = result.decision
        record.routing_reason = result.reason

    # Phase 2: cascade loop
    for _round in range(MAX_CASCADE_ROUNDS):
        # Collect records that need dispatch this round
        to_dispatch: List[tuple] = []
        for record in records:
            route = route_name_from_decision(record.routing_decision)
            if route is None:
                continue

            if _already_routed(record, route):
                continue

            handler = active_handlers.get(route)
            if handler is None:
                old_reason = record.routing_reason
                record.routing_reason = (
                    f"{old_reason} (no handler registered for route '{route}')"
                )
                # Re-decide: treat missing handler like a silent verdict so
                # the next candidate route (if any) is tried.
                _redecide(record, available_routes, policy)
                continue

            to_dispatch.append((record, handler, route))

        if not to_dispatch:
            break

        # Snapshot which route each dispatched record is attempting, and
        # how many route_verdicts it has before the handler runs.
        pre_counts = {id(r): len(r.route_verdicts) for r, _, _ in to_dispatch}
        dispatched_routes = {id(r): rt for r, _, rt in to_dispatch}

        # Dispatch concurrently
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_ROUTES)

        async def _run_handler(
            rec: ClaimRecord, hdlr: RouteHandler, rt: str,
        ) -> None:
            async with semaphore:
                try:
                    await hdlr(rec)
                except Exception as exc:  # noqa: BLE001
                    rec.routing_reason = f"{rec.routing_reason} (handler error: {exc})"
                    logger.exception(
                        "execute_routing: handler for route '%s' failed", rt,
                    )
                    # Record a synthetic failed verdict so _already_routed
                    # skips this route on cascade re-decide.
                    rec.route_verdicts.append(
                        RouteVerdict(
                            route=rt,
                            verdict="handler_error",
                            reasoning=f"Handler raised: {exc}",
                        )
                    )

        await asyncio.gather(
            *[_run_handler(r, h, rt) for r, h, rt in to_dispatch],
        )

        # Check for silent / missing verdicts -> re-decide for next round
        needs_escalation = False
        for record in records:
            rec_id = id(record)
            if rec_id not in dispatched_routes:
                continue

            attempted_route = dispatched_routes[rec_id]
            pre_count = pre_counts[rec_id]

            # Determine if the handler produced a decisive (non-silent) verdict
            # for the route it was dispatched to.
            new_verdicts = record.route_verdicts[pre_count:]
            route_verdict_added = [
                rv for rv in new_verdicts if rv.route == attempted_route
            ]

            if route_verdict_added:
                latest = route_verdict_added[-1]
                if not _is_cascade_silent(latest.verdict):
                    # Decisive result -- update routing_decision to reflect
                    # the route that actually resolved the claim.
                    record.routing_decision = route_decision(attempted_route)
                    continue
            else:
                # Handler returned without appending a verdict for this
                # route (returned None, or populated a different route).
                # Record a synthetic verdict so _already_routed skips
                # this route on cascade re-decide.
                record.route_verdicts.append(
                    RouteVerdict(
                        route=attempted_route,
                        verdict="handler_error",
                        reasoning="Handler returned no verdict",
                    )
                )

            # Silent, no verdict, or handler error -- escalate
            if _redecide(record, available_routes, policy):
                needs_escalation = True

        if not needs_escalation:
            break

    return records


def _redecide(
    record: ClaimRecord,
    available_routes: List[str],
    policy: Optional[List[PolicyRow]],
) -> bool:
    """Re-run ``decide_route`` for cascade escalation.

    Updates ``routing_decision`` and appends cascade context to
    ``routing_reason``. Returns True if the new decision is a route
    (meaning another dispatch round is needed).
    """
    old_reason = record.routing_reason or ""
    result = decide_route(record, available_routes, policy=policy)
    record.routing_decision = result.decision
    record.routing_reason = f"{old_reason}; cascade: {result.reason}"
    return route_name_from_decision(result.decision) is not None


# ---------------------------------------------------------------------------
# Importance-gated cross-checks (TG 05.3)
# ---------------------------------------------------------------------------

CROSS_CHECK_IMPORTANCE_THRESHOLD = 4


def _needs_d4(record: ClaimRecord) -> bool:
    """D4: vault-resolved, cited, importance >= threshold, corpus not yet attempted."""
    if (record.importance or 0) < CROSS_CHECK_IMPORTANCE_THRESHOLD:
        return False
    if record.citation_status != CitationStatus.CITED or not record.cite_set:
        return False
    if not any(
        rv.verdict
        in (VaultVerdict.VAULT_SUPPORTED.value, VaultVerdict.VAULT_CONTRADICTED.value)
        for rv in record.route_verdicts
    ):
        return False
    if _already_routed(record, "corpus"):
        return False
    return True


# Routes whose verdicts count toward D10's "already has a support verdict"
# check -- the vault and corpus routes (never web: a claim already routed
# to web is excluded by `_already_routed(record, "web")` below, not by this
# set).
_D10_SUPPORT_SOURCE_ROUTES = frozenset({"vault_aligned", "vault_matched", "corpus"})


def _needs_support_confirm(record: ClaimRecord) -> bool:
    """D10 (Session 12 amendment): support verdict, importance >= threshold,
    web-eligible, web not yet attempted -> one web confirmation check.

    Supersedes D5's "supports never trigger routine cross-checks" guardrail
    for importance >= threshold claims: a false fact shared by the author's
    vault and draft previously sailed through with no independent check.
    Mixed support+refute still fires -- web arbitrates -- so this does NOT
    check for the absence of a refuting verdict.
    """
    if not SUPPORT_CONFIRMATION_ENABLED:
        return False
    if (record.importance or 0) < CROSS_CHECK_IMPORTANCE_THRESHOLD:
        return False
    if record.triage_class in NEVER_WEB_CLASSES:
        return False
    if _already_routed(record, "web"):
        return False
    return any(
        rv.route in _D10_SUPPORT_SOURCE_ROUTES and normalize_verdict(rv.verdict) == NORM_SUPPORT
        for rv in record.route_verdicts
    )


def _needs_d5(record: ClaimRecord) -> bool:
    """D5: single-lineage refutation, importance >= threshold, web-eligible, web not yet attempted."""
    if (record.importance or 0) < CROSS_CHECK_IMPORTANCE_THRESHOLD:
        return False
    if record.triage_class in NEVER_WEB_CLASSES:
        return False
    if _already_routed(record, "web"):
        return False
    has_refute = any(
        normalize_verdict(rv.verdict) == NORM_REFUTE for rv in record.route_verdicts
    )
    if not has_refute:
        return False
    has_support = any(
        normalize_verdict(rv.verdict) == NORM_SUPPORT for rv in record.route_verdicts
    )
    if has_support:
        return False
    return True


async def apply_cross_checks(
    records: List[ClaimRecord],
    manifest: ResourceManifest,
    handlers: Dict[str, RouteHandler],
) -> List[ClaimRecord]:
    """Apply importance-gated cross-checks (D4, D5) after cascade routing.

    D4 — Attribution check: vault-resolved + cited + importance >= 4 +
    corpus handler available → scoped corpus check (does the source
    actually say this?).

    D5 — Refutation confirmation: single-tier refutation + importance >= 4
    + web-eligible → one web check for independent confirmation.
    Never-web claims are left as single-lineage.

    D10 (Session 12 amendment) — Support confirmation: a support verdict
    (vault or corpus) + importance >= 4 + web-eligible + web not yet
    attempted → one web confirmation check. Supersedes D5's original
    "supports never trigger cross-checks" guardrail for important claims;
    gated by config.toml's ``pipeline.support_confirmation``
    (``SUPPORT_CONFIRMATION_ENABLED``, default on).

    Modifies and returns ``records`` in place.
    """
    d4_dispatch: List[tuple] = []
    d5_dispatch: List[tuple] = []
    d10_dispatch: List[tuple] = []

    corpus_handler = handlers.get("corpus")
    web_handler = handlers.get("web")

    for record in records:
        if corpus_handler and _needs_d4(record):
            d4_dispatch.append((record, corpus_handler, "corpus"))
        if web_handler and _needs_d5(record):
            d5_dispatch.append((record, web_handler, "web"))
        if web_handler and _needs_support_confirm(record):
            d10_dispatch.append((record, web_handler, "web"))

    all_dispatch = d4_dispatch + d5_dispatch + d10_dispatch
    if not all_dispatch:
        return records

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_ROUTES)

    async def _run(rec: ClaimRecord, hdlr: RouteHandler, route: str) -> None:
        async with semaphore:
            try:
                await hdlr(rec)
            except Exception as exc:  # noqa: BLE001
                rec.routing_reason = (
                    f"{rec.routing_reason or ''}; cross-check {route} error: {exc}"
                )
                logger.exception(
                    "apply_cross_checks: handler for route '%s' failed", route,
                )

    await asyncio.gather(*[_run(r, h, rt) for r, h, rt in all_dispatch])

    return records
