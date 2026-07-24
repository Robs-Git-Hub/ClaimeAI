"""Live spot-check for TG 02.4 (alignment) and TG 02.5 (vault matching).

Runs against the real ukraine vault with OpenRouter. Requires:
  - OPENROUTER_API_KEY in .env
  - ../ukraine-vote-analysis/vault-main/ (sibling repo)

Usage:
    LLM_PROVIDER=openrouter python scripts/spot_check_vault.py
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

os.environ["LLM_PROVIDER"] = "openrouter"

from claim_verifier.schemas import Verdict, VerificationResult
from ingest.alignment import evaluate_alignment
from ingest.draft_parser import parse_draft
from ingest.gap_report import assign_suggested_actions, render_gap_report
from ingest.vault_match import batch_match_claims, verify_matches
from ingest.vault_serializer import (
    DEFAULT_EVIDENCE_TYPES,
    load_vault,
    serialize_vault,
)
from utils.claim_record import (
    CitationStatus,
    ClaimRecord,
    DraftPosition,
)
from utils.run_config import ResourceManifest


VAULT_PATH = Path(__file__).resolve().parent.parent.parent / "ukraine-vote-analysis" / "vault-main"
TEST_FILE = Path(__file__).resolve().parent.parent / "workspace" / "inbox" / "ukraine-rich-wikilinks-test.md"
ARGUMENT_PYRAMID = "un-ukraine-russia-war-votes-working-paper"


def make_claim_record(sentence, index):
    verdict = Verdict(
        claim_text=sentence.clean_text,
        disambiguated_sentence=sentence.clean_text,
        original_sentence=sentence.original_text,
        original_index=sentence.sentence_index,
        result=VerificationResult.SUPPORTED,
        reasoning="Synthetic verdict for spot-check.",
        sources=[],
    )
    return ClaimRecord(
        web_verdict=verdict,
        citation_status=sentence.citation_status,
        cite_set=sentence.cite_set,
        position=DraftPosition(sentence_index=sentence.sentence_index),
    )


async def main():
    print("=" * 70)
    print("VAULT SPOT-CHECK")
    print("=" * 70)

    # Load filtered vault (argument_pyramid + evidence types)
    print(f"\nLoading vault from {VAULT_PATH} ...")
    filtered_notes = load_vault(
        VAULT_PATH,
        argument_pyramid=ARGUMENT_PYRAMID,
        evidence_types=DEFAULT_EVIDENCE_TYPES,
    )
    filtered_vault = {n.name: n for n in filtered_notes}
    print(f"  Filtered: {len(filtered_notes)} notes (argument_pyramid={ARGUMENT_PYRAMID})")

    # Load full vault (no filters) as fallback for cited-note lookup
    all_notes = load_vault(VAULT_PATH)
    full_vault = {n.name: n for n in all_notes}
    print(f"  Full: {len(all_notes)} notes (unfiltered)")

    # Parse test file
    print(f"\nParsing {TEST_FILE.name} ...")
    text = TEST_FILE.read_text(encoding="utf-8")
    draft = parse_draft(text)
    all_cites = sum(len(s.cite_set) for s in draft.sentences)
    print(f"  {len(draft.sentences)} sentences, {all_cites} wikilink citations")

    # Build claim records
    records = [make_claim_record(s, i) for i, s in enumerate(draft.sentences)]
    cited = [r for r in records if r.citation_status == CitationStatus.CITED]
    citation_free = [r for r in records if r.citation_status == CitationStatus.CITATION_FREE]
    print(f"  {len(cited)} cited, {len(citation_free)} citation-free")

    # --- TG 02.4: Alignment (with full vault fallback) ---
    print("\n" + "-" * 70)
    print("TG 02.4: CITED-CLAIM ALIGNMENT")
    print("-" * 70)

    for record in cited:
        print(f"\n  Claim: {record.web_verdict.claim_text[:80]}...")
        print(f"  Cite set: {record.cite_set}")
        record = await evaluate_alignment(record, filtered_vault, full_vault)
        for rv in record.route_verdicts:
            print(f"    -> [{rv.verdict}] provenance={rv.provenance}")
            if rv.reasoning:
                print(f"       {rv.reasoning[:120]}")

    # --- TG 02.5: Citation-free matching ---
    print("\n" + "-" * 70)
    print("TG 02.5: CITATION-FREE VAULT MATCHING")
    print("-" * 70)

    serialized = serialize_vault(filtered_notes)
    print(f"\n  Serialized vault: {serialized.note_count} notes, ~{serialized.token_estimate} tokens")

    print("\n  Stage 1: Batch matching ...")
    proposals = await batch_match_claims(records, serialized)
    print(f"  Got {len(proposals)} proposals")
    for p in proposals:
        claim_text = records[p.claim_index].web_verdict.claim_text if 0 <= p.claim_index < len(records) else "???"
        print(f"    [{p.claim_index}] {claim_text[:60]}... -> {p.note_name}")

    if proposals:
        print("\n  Stage 2: Verifying matches ...")
        records = await verify_matches(records, proposals, filtered_vault)
        for record in records:
            for rv in record.route_verdicts:
                if rv.route == "vault_matched":
                    print(f"    [{rv.verdict}] {record.web_verdict.claim_text[:60]}...")
                    print(f"       provenance={rv.provenance}")
                    if rv.reasoning:
                        print(f"       {rv.reasoning[:120]}")
                    if record.claim_strength is not None:
                        print(f"       claim_strength={record.claim_strength}, evidence_quality={record.evidence_quality}")

    # --- TG 02.6: Gap Report ---
    print("\n" + "-" * 70)
    print("TG 02.6: GAP REPORT")
    print("-" * 70)

    assign_suggested_actions(records)
    manifest = ResourceManifest(
        draft_path=TEST_FILE,
        vault_path=VAULT_PATH,
        argument_pyramid=ARGUMENT_PYRAMID,
    )
    report = render_gap_report(records, manifest)
    output_path = Path(__file__).resolve().parent.parent / "workspace" / "output" / "spot-check-report.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"\n  Report written to {output_path}")

    action_counts = {}
    for r in records:
        action = r.suggested_action.value if r.suggested_action else "none"
        action_counts[action] = action_counts.get(action, 0) + 1
    print("\n  Action summary:")
    for action, count in sorted(action_counts.items()):
        print(f"    {action}: {count}")

    print("\n" + "=" * 70)
    print("SPOT-CHECK COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
