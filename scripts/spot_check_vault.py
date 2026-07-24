"""Live spot-check for TG 02.4 (alignment) and TG 02.5 (vault matching).

Runs against the real ukraine vault with OpenRouter. Requires:
  - OPENROUTER_API_KEY in .env
  - ../ukraine-vote-analysis/vault-main/ (sibling repo)

Usage:
    LLM_PROVIDER=openrouter python scripts/spot_check_vault.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Load .env before any imports that read settings
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Override provider to openrouter
os.environ["LLM_PROVIDER"] = "openrouter"

from claim_verifier.schemas import Verdict, VerificationResult
from ingest.alignment import evaluate_alignment
from ingest.draft_parser import parse_draft
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
    print("VAULT SPOT-CHECK: TG 02.4 (alignment) + TG 02.5 (matching)")
    print("=" * 70)

    # Load vault
    print(f"\nLoading vault from {VAULT_PATH} ...")
    vault_notes = load_vault(
        VAULT_PATH,
        argument_pyramid=ARGUMENT_PYRAMID,
        evidence_types=DEFAULT_EVIDENCE_TYPES,
    )
    vault_by_name = {n.name: n for n in vault_notes}
    print(f"  Loaded {len(vault_notes)} notes (filtered by argument_pyramid={ARGUMENT_PYRAMID})")

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

    # --- TG 02.4: Alignment ---
    print("\n" + "-" * 70)
    print("TG 02.4: CITED-CLAIM ALIGNMENT")
    print("-" * 70)

    for record in cited:
        print(f"\n  Claim: {record.web_verdict.claim_text[:80]}...")
        print(f"  Cite set: {record.cite_set}")
        record = await evaluate_alignment(record, vault_by_name)
        for rv in record.vault_verdicts:
            print(f"    -> [{rv.verdict}] provenance={rv.provenance}")
            if rv.reasoning:
                print(f"       {rv.reasoning[:120]}")

    # --- TG 02.5: Citation-free matching ---
    print("\n" + "-" * 70)
    print("TG 02.5: CITATION-FREE VAULT MATCHING")
    print("-" * 70)

    serialized = serialize_vault(vault_notes)
    print(f"\n  Serialized vault: {serialized.note_count} notes, ~{serialized.token_estimate} tokens")

    print("\n  Stage 1: Batch matching ...")
    proposals = await batch_match_claims(records, serialized)
    print(f"  Got {len(proposals)} proposals")
    for p in proposals:
        claim_text = records[p.claim_index].web_verdict.claim_text if 0 <= p.claim_index < len(records) else "???"
        print(f"    [{p.claim_index}] {claim_text[:60]}... -> {p.note_name}")

    if proposals:
        print("\n  Stage 2: Verifying matches ...")
        records = await verify_matches(records, proposals, vault_by_name)
        for record in records:
            for rv in record.vault_verdicts:
                if rv.route == "vault_matched":
                    print(f"    [{rv.verdict}] {record.web_verdict.claim_text[:60]}...")
                    print(f"       provenance={rv.provenance}")
                    if rv.reasoning:
                        print(f"       {rv.reasoning[:120]}")
                    if record.claim_strength is not None:
                        print(f"       claim_strength={record.claim_strength}, evidence_quality={record.evidence_quality}")

    print("\n" + "=" * 70)
    print("SPOT-CHECK COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
