"""Gap report v2 (TG 02.6).

Three functions:
    1. ``assign_suggested_actions`` — pure, synchronous. Computes a
       `SuggestedAction` for each `ClaimRecord` from its web/vault
       verdicts, in a fixed priority order.
    2. ``serialize_results`` — the machine-readable results.json payload
       (the full claim records, as JSON-serializable dicts).
    3. ``render_gap_report`` — the human-readable markdown report.
       Sections adapt to the manifest: no vault declared -> no vault
       sections (not empty ones), keeping the light-profile report
       backward compatible with Phase 01's format.

Every verdict rendered must carry provenance -- no naked "supported".
"""

from collections import Counter
from datetime import datetime
from typing import Any, Dict, List

from claim_verifier.schemas import VerificationResult
from ingest.routing import (
    NEVER_WEB_CLASSES,
    NORM_REFUTE,
    NORM_SUPPORT,
    SKIP_TRIVIAL,
    UNVERIFIABLE,
    normalize_verdict,
    route_name_from_decision,
)
from utils.claim_record import (
    CitationStatus,
    ClaimRecord,
    SuggestedAction,
    VaultVerdict,
)
from utils.run_config import ResourceManifest

# ---------------------------------------------------------------------------
# Lineage groups (TG 05.4)
# ---------------------------------------------------------------------------
#
# "Shared" lineage routes ultimately trace back to the same underlying
# corpus the author curated (vault notes, or the author's own ingested
# paper corpus) -- they are not independent of each other or of the
# author's judgment. "web" is the only independent-lineage route: it
# checks the claim against sources the author didn't select.

SHARED_LINEAGE_ROUTES = frozenset({"vault_aligned", "vault_matched", "corpus"})
VAULT_ROUTES = frozenset({"vault_aligned", "vault_matched"})
WEB_ROUTE = "web"
CORPUS_ROUTE = "corpus"

SOURCE_CONFLICT = "source-conflict"
VAULT_CORPUS_CHECK_NEEDED = "vault-corpus-check-needed"


def _normalized_verdicts_for_routes(record: ClaimRecord, routes: frozenset) -> List[str]:
    return [
        normalize_verdict(rv.verdict) for rv in record.route_verdicts if rv.route in routes
    ]


def _opposing(a: List[str], b: List[str]) -> bool:
    """Whether `a` and `b` disagree: one side supports, the other refutes.

    Silent/unknown normalized verdicts never count toward either side, so
    an empty or all-silent group can never trigger a conflict.
    """
    a_support, a_refute = NORM_SUPPORT in a, NORM_REFUTE in a
    b_support, b_refute = NORM_SUPPORT in b, NORM_REFUTE in b
    return (a_support and b_refute) or (a_refute and b_support)


def detect_conflicts(records: List[ClaimRecord]) -> List[ClaimRecord]:
    """Detect support-vs-refute disagreements between evidence tiers.

    Pure, synchronous, LLM-free. Sets ``conflict_flags`` on each record.

    Two flags:
        - ``"source-conflict"`` -- a web verdict disagrees (support vs.
          refute) with a vault or corpus verdict. The highest-value
          finding: an independent check contradicts the author's own
          source.
        - ``"vault-corpus-check-needed"`` -- a vault verdict disagrees
          with a corpus verdict. Both are shared-lineage (the author's own
          materials), so this is a "re-read the source" signal rather
          than an independent contradiction.

    Only clear support-vs-refute disagreement triggers a flag; silent or
    unrecognized verdicts never do (`normalize_verdict` maps both to
    "silent"). Modifies and returns ``records`` in place.
    """
    for record in records:
        shared_verdicts = _normalized_verdicts_for_routes(record, SHARED_LINEAGE_ROUTES)
        web_verdicts = _normalized_verdicts_for_routes(record, frozenset({WEB_ROUTE}))
        vault_verdicts = _normalized_verdicts_for_routes(record, VAULT_ROUTES)
        corpus_verdicts = _normalized_verdicts_for_routes(record, frozenset({CORPUS_ROUTE}))

        flags: List[str] = []
        if _opposing(shared_verdicts, web_verdicts):
            flags.append(SOURCE_CONFLICT)
        if _opposing(vault_verdicts, corpus_verdicts):
            flags.append(VAULT_CORPUS_CHECK_NEEDED)

        record.conflict_flags = flags

    return records


# ---------------------------------------------------------------------------
# assign_suggested_actions
# ---------------------------------------------------------------------------


def assign_suggested_actions(records: List[ClaimRecord]) -> List[ClaimRecord]:
    """Compute and set ``suggested_action`` on every record, in place.

    Priority order (first match wins):
        1. ``"source-conflict"`` in ``conflict_flags`` -> ``REVISE_CLAIM``.
           A cross-tier disagreement outranks any individual verdict --
           run ``detect_conflicts`` before this function for the flag to
           be populated.
        2. Any vault verdict is ``vault_contradicted`` -> ``REVISE_CLAIM``.
        3. Cited claim with a ``not_supported`` vault verdict (miscite)
           -> ``FIX_CITATION``.
        4. Any vault verdict is ``vault_supported`` -> ``NONE``.
        5. Web-supported but no vault support -> ``ADD_VAULT_NOTE`` (vault
           improvement signal).
        6. Citation-free claim with no vault match -> ``ADD_CITATION``.
        7. Otherwise -> ``UNRESOLVED``.
    """
    for record in records:
        route_verdicts = record.route_verdicts

        if SOURCE_CONFLICT in record.conflict_flags:
            record.suggested_action = SuggestedAction.REVISE_CLAIM
            continue

        if any(
            rv.verdict == VaultVerdict.VAULT_CONTRADICTED.value
            for rv in route_verdicts
        ):
            record.suggested_action = SuggestedAction.REVISE_CLAIM
            continue

        if record.citation_status == CitationStatus.CITED and any(
            rv.verdict == VaultVerdict.NOT_SUPPORTED.value for rv in route_verdicts
        ):
            record.suggested_action = SuggestedAction.FIX_CITATION
            continue

        if any(
            rv.verdict == VaultVerdict.VAULT_SUPPORTED.value for rv in route_verdicts
        ):
            record.suggested_action = SuggestedAction.NONE
            continue

        web_verdict = record.web_verdict
        if (
            web_verdict is not None
            and web_verdict.result == VerificationResult.SUPPORTED
        ):
            record.suggested_action = SuggestedAction.ADD_VAULT_NOTE
            continue

        no_vault_match = not route_verdicts or all(
            rv.verdict == VaultVerdict.NO_VAULT_MATCH.value for rv in route_verdicts
        )
        if record.citation_status == CitationStatus.CITATION_FREE and no_vault_match:
            record.suggested_action = SuggestedAction.ADD_CITATION
            continue

        record.suggested_action = SuggestedAction.UNRESOLVED

    return records


# ---------------------------------------------------------------------------
# serialize_results
# ---------------------------------------------------------------------------


def serialize_results(records: List[ClaimRecord]) -> List[Dict[str, Any]]:
    """Return the full claim records as JSON-serializable dicts."""
    return [record.model_dump() for record in records]


# ---------------------------------------------------------------------------
# render_gap_report
# ---------------------------------------------------------------------------

_ACTION_LABELS = [
    (SuggestedAction.NONE, "No action needed"),
    (SuggestedAction.FIX_CITATION, "Fix citation (miscite)"),
    (SuggestedAction.ADD_CITATION, "Add citation"),
    (SuggestedAction.ADD_VAULT_NOTE, "Add vault note"),
    (SuggestedAction.REVISE_CLAIM, "Revise claim"),
    (SuggestedAction.UNRESOLVED, "Unresolved"),
]


def _md_cell(value: Any) -> str:
    """Make a value safe to embed in markdown (escape pipes/newlines)."""
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _action_tag(action: SuggestedAction) -> str:
    return action.value.replace("_", "-").upper()


def _action_label(action: SuggestedAction) -> str:
    return action.value.replace("_", "-")


def _claim_text(record: ClaimRecord) -> str:
    return record.claim_text or "(no claim text)"


def _render_summary(records: List[ClaimRecord]) -> List[str]:
    counts = Counter(record.suggested_action for record in records)
    lines = ["## Summary", "", "| Action | Count |", "|--------|-------|"]
    for action, label in _ACTION_LABELS:
        lines.append(f"| {label} | {counts.get(action, 0)} |")
    lines.append("")
    return lines


def _has_routing_data(records: List[ClaimRecord]) -> bool:
    """Whether any record carries triage/routing data (i.e. TG 03.3 ran)."""
    return any(
        record.routing_decision is not None or record.triage_class is not None
        for record in records
    )


def _render_route_summary(records: List[ClaimRecord]) -> List[str]:
    """The cost/route story (TG 03.3): decisions, routes taken, web avoided.

    "Web calls avoided" is defined per the phase plan as the claims that
    Phase 01's uniform treatment would have sent to web but this run kept
    off it by triage: skip-trivial claims plus never-web (novel-result /
    dataset-dependent) claims.
    """
    lines = ["## Route summary", ""]

    decisions = Counter(record.routing_decision or "(no decision)" for record in records)
    lines.append("| Routing decision | Count |")
    lines.append("|------------------|-------|")
    for decision, count in sorted(decisions.items()):
        lines.append(f"| {_md_cell(decision)} | {count} |")
    lines.append("")

    routes_taken: Counter = Counter()
    for record in records:
        name = route_name_from_decision(record.routing_decision or "")
        if name:
            routes_taken[name] += 1

    lines.append("### Routes taken")
    lines.append("")
    if routes_taken:
        for route, count in sorted(routes_taken.items()):
            lines.append(f"- {route}: {count}")
    else:
        lines.append("- None")
    lines.append("")

    skip_trivial = sum(1 for r in records if r.routing_decision == SKIP_TRIVIAL)
    never_web = sum(1 for r in records if r.triage_class in NEVER_WEB_CLASSES)
    avoided = skip_trivial + never_web
    web_made = routes_taken.get("web", 0)

    lines.append("### Web calls avoided vs. Phase 01 baseline")
    lines.append("")
    lines.append(f"- Web calls made this run: {web_made}")
    lines.append(
        f"- Web calls avoided by triage: {avoided} "
        f"(skip-trivial: {skip_trivial}, never-web: {never_web})"
    )
    lines.append(
        f"- Phase 01 uniform treatment would web-check all {len(records)} claim(s)."
    )
    lines.append("")
    return lines


def _render_web_verdict(record: ClaimRecord) -> str:
    if record.web_verdict is None:
        return "**Web verdict:** not checked"
    sources = ", ".join(
        s.url for s in record.web_verdict.sources if s.url
    ) or "no sources listed"
    return f"**Web verdict:** {record.web_verdict.result.value} — sources: {sources}"


def _is_single_lineage(record: ClaimRecord) -> bool:
    """Whether this claim's only verdicts come from shared lineage (D8).

    True when every route that produced a verdict is vault/corpus (never
    web), at least one such route exists, and the claim wasn't skipped as
    trivial or left unverifiable -- in both of those cases there's no
    "independent check that didn't happen" story worth flagging. Not a
    stored field: derived at render time from ``route_verdicts``.
    """
    routes = {rv.route for rv in record.route_verdicts}
    if not routes or WEB_ROUTE in routes:
        return False
    if not routes & SHARED_LINEAGE_ROUTES:
        return False
    if record.triage_class == "trivial":
        return False
    if record.routing_decision == UNVERIFIABLE:
        return False
    return True


def _render_route_verdicts(record: ClaimRecord) -> List[str]:
    header = "**Route verdicts:**"
    if _is_single_lineage(record):
        header += " (single-lineage)"
    lines = [header]
    if not record.route_verdicts:
        lines.append("- (no route verdicts)")
        return lines
    for rv in record.route_verdicts:
        provenance = rv.provenance or "no provenance"
        reasoning = rv.reasoning or "no reasoning given"
        lines.append(
            f"- [{rv.route}] {rv.verdict} — provenance: {provenance} — {reasoning}"
        )
    return lines


def _render_source_conflict(record: ClaimRecord) -> List[str]:
    """Side-by-side provenance for a source-conflict claim (D7).

    Emits nothing unless ``"source-conflict"`` is in ``conflict_flags``
    (run ``detect_conflicts`` first) -- purely additive to the claim
    detail section otherwise.
    """
    if SOURCE_CONFLICT not in record.conflict_flags:
        return []

    lines = ["**Source conflict:** independent web check disagrees with shared-lineage evidence"]
    for rv in record.route_verdicts:
        if rv.route not in SHARED_LINEAGE_ROUTES:
            continue
        provenance = rv.provenance or "no provenance"
        lines.append(f"- [{rv.route}] {rv.verdict} — {provenance}")
    for rv in record.route_verdicts:
        if rv.route != WEB_ROUTE:
            continue
        provenance = rv.provenance or "no provenance"
        lines.append(f"- [web] {rv.verdict} — {provenance}")
    return lines


def _render_triage_routing(record: ClaimRecord) -> List[str]:
    """Per-claim triage class + routing decision lines (TG 03.3).

    Emits nothing when neither field is populated, so Phase 02-style records
    (no triage/routing run) render exactly as before.
    """
    lines: List[str] = []
    if record.triage_class is not None or record.importance is not None:
        importance = (
            f" (importance {record.importance})" if record.importance is not None else ""
        )
        lines.append(f"**Triage:** {record.triage_class or 'unclassified'}{importance}")
    if record.routing_decision is not None:
        reason = f" — {_md_cell(record.routing_reason)}" if record.routing_reason else ""
        lines.append(f"**Routing:** {_md_cell(record.routing_decision)}{reason}")
    return lines


def _render_claims(records: List[ClaimRecord], has_vault: bool) -> List[str]:
    lines = ["## Claims", ""]
    for index, record in enumerate(records, start=1):
        action = record.suggested_action or SuggestedAction.UNRESOLVED
        lines.append(
            f"### {index}. [{_action_tag(action)}] {_md_cell(_claim_text(record))}"
        )
        lines.append("")
        lines.append(
            f"**Status:** {record.citation_status.value.replace('_', '-')}"
        )
        lines.extend(_render_triage_routing(record))
        lines.append(_render_web_verdict(record))
        if has_vault:
            lines.extend(_render_route_verdicts(record))
            lines.extend(_render_source_conflict(record))
        lines.append(f"**Suggested action:** {_action_label(action)}")
        lines.append("")
        lines.append("---")
        lines.append("")
    return lines


def _render_vault_signals(records: List[ClaimRecord]) -> List[str]:
    lines = ["## Vault Improvement Signals", ""]

    lines.append("### Notes not in vault")
    lines.append("")
    not_in_vault = [
        (rv.provenance or "unknown note", index)
        for index, record in enumerate(records, start=1)
        for rv in record.route_verdicts
        if rv.verdict == VaultVerdict.NOTE_NOT_IN_VAULT.value
    ]
    if not_in_vault:
        for note, index in not_in_vault:
            lines.append(f"- {note} (cited by claim #{index})")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("### Notes with insufficient content")
    lines.append("")
    insufficient = [
        (rv.provenance or "unknown note", index)
        for index, record in enumerate(records, start=1)
        for rv in record.route_verdicts
        if rv.verdict == VaultVerdict.INSUFFICIENT_VAULT_CONTENT.value
    ]
    if insufficient:
        for note, index in insufficient:
            lines.append(f"- {note} (cited by claim #{index}, needs quote extraction)")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("### Notes matched outside the paper filter")
    lines.append("")
    fallback_matches = [
        (rv.provenance or "unknown note", index)
        for index, record in enumerate(records, start=1)
        for rv in record.route_verdicts
        if rv.provenance_type == "vault_note_fallback"
    ]
    if fallback_matches:
        for note, index in fallback_matches:
            lines.append(
                "- Notes matched outside the paper filter — consider adding "
                f"`argument_pyramid` tag: {note} (matched claim #{index})"
            )
    else:
        lines.append("- None")
    lines.append("")

    lines.append("### Vault/corpus verdict mismatches")
    lines.append("")
    mismatches = [
        (index, record)
        for index, record in enumerate(records, start=1)
        if VAULT_CORPUS_CHECK_NEEDED in record.conflict_flags
    ]
    if mismatches:
        for index, record in mismatches:
            vault_rv = next(
                (rv for rv in record.route_verdicts if rv.route in VAULT_ROUTES), None
            )
            corpus_rv = next(
                (rv for rv in record.route_verdicts if rv.route == CORPUS_ROUTE), None
            )
            vault_verdict = vault_rv.verdict if vault_rv else "unknown"
            corpus_verdict = corpus_rv.verdict if corpus_rv else "unknown"
            lines.append(
                f"- Claim #{index}: vault says {vault_verdict}, corpus says "
                f"{corpus_verdict} — re-read the source against your note."
            )
    else:
        lines.append("- None")
    lines.append("")

    lines.append("### Claims supported by web only (vault gap)")
    lines.append("")
    web_only = [
        (index, record)
        for index, record in enumerate(records, start=1)
        if record.suggested_action == SuggestedAction.ADD_VAULT_NOTE
    ]
    if web_only:
        for index, record in web_only:
            lines.append(
                f'- Claim #{index}: "{_md_cell(_claim_text(record))}" — add vault note'
            )
    else:
        lines.append("- None")
    lines.append("")

    return lines


def render_gap_report(records: List[ClaimRecord], manifest: ResourceManifest) -> str:
    """Render the human-readable gap report as markdown.

    Omits the "Vault Improvement Signals" section (and per-claim vault
    verdicts) entirely when ``manifest.vault_path`` is None, so a light
    (vault-less) run's report matches Phase 01's format.
    """
    has_vault = manifest.has_vault
    cited_count = sum(
        1 for record in records if record.citation_status == CitationStatus.CITED
    )
    free_count = sum(
        1
        for record in records
        if record.citation_status == CitationStatus.CITATION_FREE
    )
    unparsed_count = sum(
        1
        for record in records
        if record.citation_status == CitationStatus.UNPARSED_CITATION
    )
    vault_display = str(manifest.vault_path) if has_vault else "not configured"

    header = f"Claims: {len(records)} | Cited: {cited_count} | Citation-free: {free_count}"
    if unparsed_count:
        header += f" | Unparsed citation: {unparsed_count}"

    lines: List[str] = [
        "# Gap Report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        header,
        f"Vault: {vault_display}",
        "",
    ]
    lines.extend(_render_summary(records))
    if _has_routing_data(records):
        lines.extend(_render_route_summary(records))
    lines.extend(_render_claims(records, has_vault))
    if has_vault:
        lines.extend(_render_vault_signals(records))

    return "\n".join(lines)
