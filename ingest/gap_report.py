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
    SKIP_TRIVIAL,
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
# assign_suggested_actions
# ---------------------------------------------------------------------------


def assign_suggested_actions(records: List[ClaimRecord]) -> List[ClaimRecord]:
    """Compute and set ``suggested_action`` on every record, in place.

    Priority order (first match wins):
        1. Any vault verdict is ``vault_contradicted`` -> ``REVISE_CLAIM``.
        2. Cited claim with a ``not_supported`` vault verdict (miscite)
           -> ``FIX_CITATION``.
        3. Any vault verdict is ``vault_supported`` -> ``NONE``.
        4. Web-supported but no vault support -> ``ADD_VAULT_NOTE`` (vault
           improvement signal).
        5. Citation-free claim with no vault match -> ``ADD_CITATION``.
        6. Otherwise -> ``UNRESOLVED``.
    """
    for record in records:
        route_verdicts = record.route_verdicts

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


def _render_route_verdicts(record: ClaimRecord) -> List[str]:
    lines = ["**Route verdicts:**"]
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
