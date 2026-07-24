"""Heavy-pipeline entry point (TG 03.3): draft + manifest -> gap report.

One production entry point that runs the full heavy pipeline end to end,
replacing the Phase 02 demo wiring in ``scripts/spot_check_vault.py`` (which
constructed ``ClaimRecord``s by hand and skipped Claimify extraction):

    draft (wikilinked markdown)
      -> parse_draft            (sentences + citation metadata)
      -> claim_extractor graph  (Claimify extraction, in-process ainvoke)
      -> bind_extracted_claims  (ClaimRecords carrying claim identity)
      -> vault verify           (alignment for cited, batch-match + verify
                                 for citation-free) -- only if the manifest
                                 declares a vault
      -> triage_claims          (batch classification, mid tier)
      -> execute_routing        (web route runs here when the manifest allows)
      -> assign_suggested_actions
      -> render_gap_report + serialize_results
      -> workspace/output/<stem>/{results.json,report.md}

Runs fully in-process: it invokes the ``claim_extractor`` and
``claim_verifier`` graphs directly (the pattern from
``fact_checker/nodes/extract_claims.py``), so no LangGraph dev server is
needed -- unlike the light path in ``scripts/run_from_pdf.py``.

Wave-1 integration decisions (documented per TG 03.3 brief):

1. **Record construction / honest claim identity.** The heavy pipeline
   starts from ``ValidatedClaim``s (extraction output), not web ``Verdict``s.
   A ``Verdict`` cannot carry identity without also asserting a web result
   (``result`` is required, values only Supported/Refuted), and fabricating
   one would corrupt the report (a fake "Supported" trips the
   ``ADD_VAULT_NOTE`` signal for a claim the web never checked). So identity
   was made independent of ``web_verdict``: ``ClaimRecord.claim`` holds the
   ``ValidatedClaim`` from extraction, ``web_verdict`` stays ``None`` until
   the web route actually runs, and every stage reads identity through the
   new ``ClaimRecord.claim_text`` property (prefers ``claim``, falls back to
   ``web_verdict`` so Phase 01/02 records still work). See
   ``ingest/citation_binder.py:bind_extracted_claims`` and
   ``utils/claim_record.py``.

2. **Misnamed verdict field.** ``ClaimRecord.vault_verdicts`` was renamed to
   ``route_verdicts`` across the codebase -- it always accumulated verdicts
   from *any* route (web included), and Phase 04 adds more non-vault routes.

3. **Triage skip-guard.** ``ingest/triage.py`` skips records with no claim
   text. Every record built here carries identity in ``claim``, so
   ``claim_text`` is populated and nothing is silently dropped.

Usage:
    poetry run python scripts/run_heavy.py DRAFT --vault PATH \
        [--argument-pyramid NAME] [--profile heavy|light] [--no-web]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from claim_extractor import graph as claim_extractor_graph
from ingest.citation_binder import bind_extracted_claims
from ingest.draft_parser import parse_draft
from ingest.gap_report import (
    assign_suggested_actions,
    render_gap_report,
    serialize_results,
)
from ingest.routing import execute_routing
from ingest.triage import triage_claims
from ingest.vault_match import (
    VAULT_MATCH_FALLBACK_ENABLED,
    batch_match_claims,
    batch_match_claims_fallback,
    matched_citation_free_indices,
    supersede_stale_no_match,
    verify_matches,
)
from ingest.vault_serializer import DEFAULT_EVIDENCE_TYPES, load_vault, serialize_vault
from ingest.alignment import evaluate_alignment
from utils.claim_record import CitationStatus, ClaimRecord
from utils.run_config import ResourceManifest, RunProfile

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "workspace" / "output"

PDF_EXTENSION = ".pdf"
TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}
SUPPORTED_EXTENSIONS = {PDF_EXTENSION} | TEXT_EXTENSIONS


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------


def load_draft_text(path: Path) -> str:
    """Read a draft into a single markdown string (wikilinks preserved).

    Text/markdown files are read directly; PDFs are extracted to markdown via
    Docling. Whole-draft (not per-section) so extraction sentence indices
    line up with ``parse_draft``.
    """
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return path.read_text(encoding="utf-8")
    if suffix == PDF_EXTENSION:
        from ingest import extract_pdf

        return extract_pdf(path)
    raise ValueError(
        f"Unsupported file type '{suffix or path.name}'. "
        f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )


# ---------------------------------------------------------------------------
# Pipeline (offline-testable core: no file I/O, all LLM/graph calls mockable)
# ---------------------------------------------------------------------------


async def run_pipeline(
    text: str,
    manifest: ResourceManifest,
    *,
    route_handlers: Optional[Dict[str, Any]] = None,
    policy: Optional[List[Any]] = None,
) -> Tuple[List[ClaimRecord], List[Dict[str, str]]]:
    """Compose the heavy pipeline over ``text`` given ``manifest``.

    Returns ``(records, stage_errors)``. Each LLM/graph-dependent stage is
    isolated: a failure is recorded in ``stage_errors`` and the run continues
    where meaningful (mirroring ``run_from_pdf``'s per-section error
    recording). A manifest without a vault degrades cleanly -- the vault
    stages no-op rather than error. ``route_handlers`` / ``policy`` are
    forwarded to ``execute_routing`` (handles for tests / future routes).
    """
    stage_errors: List[Dict[str, str]] = []

    def record_failure(stage: str, exc: Exception) -> None:
        logger.exception("Pipeline stage '%s' failed", stage)
        stage_errors.append({"stage": stage, "error": f"{type(exc).__name__}: {exc}"})

    # --- Parse (pure) ---
    try:
        draft = parse_draft(text)
    except Exception as exc:  # noqa: BLE001 - record and abort: nothing downstream works
        record_failure("parse_draft", exc)
        return [], stage_errors

    # --- Extract (Claimify graph, in-process) ---
    validated_claims: List[Any] = []
    try:
        extractor_result = await claim_extractor_graph.ainvoke({"answer_text": text})
        validated_claims = (extractor_result or {}).get("validated_claims", []) or []
    except Exception as exc:  # noqa: BLE001
        record_failure("extract_claims", exc)

    # --- Bind (pure) ---
    records = bind_extracted_claims(validated_claims, draft)
    if not records:
        return records, stage_errors

    # --- Vault verification (only if the manifest declares a vault) ---
    if manifest.has_vault:
        filtered_vault: Dict[str, Any] = {}
        full_vault: Dict[str, Any] = {}
        serialized = None
        try:
            filtered_notes = load_vault(
                manifest.vault_path,
                argument_pyramid=manifest.argument_pyramid,
                evidence_types=DEFAULT_EVIDENCE_TYPES,
            )
            filtered_vault = {n.name: n for n in filtered_notes}
            full_vault = {n.name: n for n in load_vault(manifest.vault_path)}
            serialized = serialize_vault(filtered_notes)
        except Exception as exc:  # noqa: BLE001
            record_failure("load_vault", exc)

        # Cited-claim alignment (per-claim isolation).
        for record in records:
            if record.citation_status != CitationStatus.CITED:
                continue
            try:
                await evaluate_alignment(record, filtered_vault, full_vault)
            except Exception as exc:  # noqa: BLE001
                record_failure(
                    f"alignment[sentence {record.position.sentence_index if record.position else '?'}]",
                    exc,
                )

        # Citation-free vault matching (batch propose -> verify).
        if serialized is not None:
            try:
                proposals = await batch_match_claims(records, serialized)
                if proposals:
                    await verify_matches(records, proposals, filtered_vault)
            except Exception as exc:  # noqa: BLE001
                record_failure("vault_match", exc)

            # Full-vault fallback (Phase 03 milestone review): the filtered
            # corpus above misses notes that support this paper but were
            # never tagged into its argument_pyramid. One extra mid-tier
            # batch call, scoped to claims still unmatched after the pass
            # above, against the full vault filtered by evidence TYPES only.
            if VAULT_MATCH_FALLBACK_ENABLED:
                try:
                    already_matched = matched_citation_free_indices(records)
                    still_unmatched = any(
                        record.citation_status == CitationStatus.CITATION_FREE
                        and record.claim_text
                        and index not in already_matched
                        for index, record in enumerate(records)
                    )
                    if still_unmatched:
                        full_type_notes = [
                            note
                            for note in full_vault.values()
                            if note.note_type in DEFAULT_EVIDENCE_TYPES
                        ]
                        fallback_proposals = await batch_match_claims_fallback(
                            records, full_type_notes, already_matched
                        )
                        if fallback_proposals:
                            full_type_vault_by_name = {
                                note.name: note for note in full_type_notes
                            }
                            await verify_matches(
                                records,
                                fallback_proposals,
                                full_type_vault_by_name,
                                provenance_type="vault_note_fallback",
                            )
                            # A fallback finding supersedes pass 1's stale
                            # no_vault_match rejection on the same route --
                            # otherwise the report renders both an absence
                            # verdict and a finding for the same claim.
                            supersede_stale_no_match(records)
                except Exception as exc:  # noqa: BLE001
                    record_failure("vault_match_fallback", exc)

    # --- Triage (batch, mid tier) ---
    try:
        await triage_claims(records)
    except Exception as exc:  # noqa: BLE001 - unclassified records degrade conservatively
        record_failure("triage", exc)

    # --- Routing (web route executes here when the manifest allows) ---
    try:
        await execute_routing(records, manifest, handlers=route_handlers, policy=policy)
    except Exception as exc:  # noqa: BLE001
        record_failure("routing", exc)

    # --- Suggested actions (pure) ---
    assign_suggested_actions(records)

    return records, stage_errors


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_outputs(
    out_dir: Path,
    records: List[ClaimRecord],
    manifest: ResourceManifest,
    stage_errors: List[Dict[str, str]],
) -> Tuple[Path, Path]:
    """Write results.json + report.md to ``out_dir`` and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "draft": str(manifest.draft_path),
        "vault": str(manifest.vault_path) if manifest.has_vault else None,
        "argument_pyramid": manifest.argument_pyramid,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "available_routes": manifest.available_routes,
        "stage_errors": stage_errors,
        "claims": serialize_results(records),
    }
    results_path = out_dir / "results.json"
    results_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    report_path = out_dir / "report.md"
    report_path.write_text(render_gap_report(records, manifest), encoding="utf-8")
    return results_path, report_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def run(manifest: ResourceManifest) -> Path:
    print(f"Reading draft {manifest.draft_path} ...")
    text = load_draft_text(manifest.draft_path)

    if manifest.has_vault:
        print(f"Vault: {manifest.vault_path} (argument_pyramid={manifest.argument_pyramid})")
    else:
        print("No vault declared -- vault verification stages will no-op.")
    print(f"Available routes: {manifest.available_routes}")

    records, stage_errors = await run_pipeline(text, manifest)
    print(f"Produced {len(records)} claim record(s).")
    if stage_errors:
        print(f"{len(stage_errors)} stage error(s) recorded (run continued):")
        for err in stage_errors:
            print(f"  - {err['stage']}: {err['error']}")

    out_dir = OUTPUT_DIR / manifest.draft_path.stem
    results_path, report_path = write_outputs(out_dir, records, manifest, stage_errors)
    print(f"Wrote {results_path}")
    print(f"Wrote {report_path}")
    return out_dir


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the heavy fact-checking pipeline (parse -> extract -> vault "
            "verify -> triage -> route) over a draft and write a gap report."
        )
    )
    parser.add_argument("draft", type=Path, help="Path to the draft (.md/.markdown/.txt/.pdf)")
    parser.add_argument(
        "--vault", type=Path, default=None, help="Path to the Obsidian vault root"
    )
    parser.add_argument(
        "--argument-pyramid",
        default=None,
        help="Vault frontmatter filter (argument_pyramid value)",
    )
    parser.add_argument(
        "--profile",
        choices=[p.value for p in RunProfile],
        default=RunProfile.HEAVY.value,
        help="light = web only (no vault); heavy = vault + web (default)",
    )
    parser.add_argument(
        "--no-web", action="store_true", help="Disable the web route (vault only)"
    )
    return parser.parse_args(argv)


def _build_manifest(args: argparse.Namespace) -> ResourceManifest:
    """Validate CLI args and build the ResourceManifest, or exit with a clear error."""
    draft_path = args.draft
    if not draft_path.is_file():
        sys.exit(f"Draft not found: {draft_path}")
    if draft_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        sys.exit(
            f"Unsupported draft type '{draft_path.suffix or draft_path.name}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    vault_path: Optional[Path] = None
    if args.profile == RunProfile.HEAVY.value:
        vault_path = args.vault
        if vault_path is not None:
            if not vault_path.exists():
                sys.exit(f"Vault path does not exist: {vault_path}")
            if not vault_path.is_dir():
                sys.exit(f"Vault path is not a directory: {vault_path}")
        else:
            print(
                "WARNING: --profile heavy with no --vault; running vault-less "
                "(no vault verification, no vault report sections).",
                file=sys.stderr,
            )
    elif args.vault is not None:
        print(
            "WARNING: --vault is ignored under --profile light (web only).",
            file=sys.stderr,
        )

    return ResourceManifest(
        draft_path=draft_path,
        vault_path=vault_path,
        argument_pyramid=args.argument_pyramid if vault_path is not None else None,
        web_enabled=not args.no_web,
    )


def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args(argv)
    manifest = _build_manifest(args)
    asyncio.run(run(manifest))


if __name__ == "__main__":
    main()
