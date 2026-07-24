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
        vault_verdicts = record.vault_verdicts

        if any(
            rv.verdict == VaultVerdict.VAULT_CONTRADICTED.value
            for rv in vault_verdicts
        ):
            record.suggested_action = SuggestedAction.REVISE_CLAIM
            continue

        if record.citation_status == CitationStatus.CITED and any(
            rv.verdict == VaultVerdict.NOT_SUPPORTED.value for rv in vault_verdicts
        ):
            record.suggested_action = SuggestedAction.FIX_CITATION
            continue

        if any(
            rv.verdict == VaultVerdict.VAULT_SUPPORTED.value for rv in vault_verdicts
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

        no_vault_match = not vault_verdicts or all(
            rv.verdict == VaultVerdict.NO_VAULT_MATCH.value for rv in vault_verdicts
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
    if record.web_verdict is not None and record.web_verdict.claim_text:
        return record.web_verdict.claim_text
    return "(no claim text)"


def _render_summary(records: List[ClaimRecord]) -> List[str]:
    counts = Counter(record.suggested_action for record in records)
    lines = ["## Summary", "", "| Action | Count |", "|--------|-------|"]
    for action, label in _ACTION_LABELS:
        lines.append(f"| {label} | {counts.get(action, 0)} |")
    lines.append("")
    return lines


def _render_web_verdict(record: ClaimRecord) -> str:
    if record.web_verdict is None:
        return "**Web verdict:** not checked"
    sources = ", ".join(
        s.url for s in record.web_verdict.sources if s.url
    ) or "no sources listed"
    return f"**Web verdict:** {record.web_verdict.result.value} — sources: {sources}"


def _render_vault_verdicts(record: ClaimRecord) -> List[str]:
    lines = ["**Vault verdicts:**"]
    if not record.vault_verdicts:
        lines.append("- (no vault verdicts)")
        return lines
    for rv in record.vault_verdicts:
        provenance = rv.provenance or "no provenance"
        reasoning = rv.reasoning or "no reasoning given"
        lines.append(
            f"- [{rv.route}] {rv.verdict} — provenance: {provenance} — {reasoning}"
        )
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
        lines.append(_render_web_verdict(record))
        if has_vault:
            lines.extend(_render_vault_verdicts(record))
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
        for rv in record.vault_verdicts
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
        for rv in record.vault_verdicts
        if rv.verdict == VaultVerdict.INSUFFICIENT_VAULT_CONTENT.value
    ]
    if insufficient:
        for note, index in insufficient:
            lines.append(f"- {note} (cited by claim #{index}, needs quote extraction)")
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
    vault_display = str(manifest.vault_path) if has_vault else "not configured"

    lines: List[str] = [
        "# Gap Report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Claims: {len(records)} | Cited: {cited_count} | Citation-free: {free_count}",
        f"Vault: {vault_display}",
        "",
    ]
    lines.extend(_render_summary(records))
    lines.extend(_render_claims(records, has_vault))
    if has_vault:
        lines.extend(_render_vault_signals(records))

    return "\n".join(lines)
