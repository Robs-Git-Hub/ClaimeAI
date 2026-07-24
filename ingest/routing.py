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

from utils.claim_record import ClaimRecord, RouteVerdict, VaultVerdict
from utils.run_config import ResourceManifest

logger = logging.getLogger(__name__)

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
            "web, regardless of anything else. No route is declared for these classes "
            "yet, so they land on unverifiable-by-available-routes until Phase 04's "
            "corpus route exists (adding it here is a one-line change: "
            'candidate_routes=("corpus",)).'
        ),
        applies=_is_never_web,
        candidate_routes=(),
    ),
    PolicyRow(
        name="general",
        condition=(
            "Otherwise (general-factual, academic-citable, or unclassified/None -- "
            "ties break toward verifying, never toward skipping) -> route to web if "
            "available and not already attempted; else unverifiable."
        ),
        applies=_catch_all,
        candidate_routes=("web",),
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
    a row's `candidate_routes` is empty by design (the "never-web" row: no
    route is ever a candidate for novel-result/dataset-dependent claims).
    Instead of showing that empty post-exclusion list, name the route
    that's being excluded and show the manifest's actual available routes,
    so the message explains *why* on its own.
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
        f"{row.name}: candidate route(s) {candidates_display} unavailable or "
        "already attempted; no other available route can verify this claim "
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

    `decide_route` is applied to every record sequentially first -- it's a
    pure, fast, synchronous decision, and every record (including ones that
    don't need a handler: resolved, skip-trivial, unverifiable) must have its
    `routing_decision`/`routing_reason` set before any handler runs. Only the
    actual handler invocations -- the slow, network-bound part -- are then
    dispatched concurrently, bounded by `MAX_CONCURRENT_ROUTES` so we don't
    fire an unbounded burst of API calls at once.
    """
    active_handlers = handlers if handlers is not None else ROUTE_HANDLERS
    available_routes = manifest.available_routes

    to_dispatch: List[tuple] = []
    for record in records:
        result = decide_route(record, available_routes, policy=policy)
        record.routing_decision = result.decision
        record.routing_reason = result.reason

        route = route_name_from_decision(result.decision)
        if route is None:
            continue

        handler = active_handlers.get(route)
        if handler is None:
            record.routing_reason = (
                f"{result.reason} (no handler registered for route '{route}')"
            )
            continue

        to_dispatch.append((record, handler, route, result.reason))

    if not to_dispatch:
        return records

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_ROUTES)

    async def _run_handler(record: ClaimRecord, handler: RouteHandler, route: str, reason: str) -> None:
        async with semaphore:
            try:
                await handler(record)
            except Exception as exc:  # noqa: BLE001 - one claim's failure must not abort the run
                record.routing_reason = f"{reason} (handler error: {exc})"
                logger.exception("execute_routing: handler for route '%s' failed", route)

    await asyncio.gather(
        *[_run_handler(record, handler, route, reason) for record, handler, route, reason in to_dispatch]
    )

    return records
