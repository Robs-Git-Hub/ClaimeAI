"""Citation-free vault matching (TG 02.5).

For claims WITHOUT a wikilink citation (`CitationStatus.CITATION_FREE`),
propose candidate claim<->note matches against the vault in bulk (one cheap
LLM call), then verify each proposed match independently and expensively.

Two-step design, mirroring `ingest/alignment.py`'s two-step shape:
    1. ``batch_match_claims`` — one LLM call (``mid`` tier — cheaper, large
       context) with ALL citation-free claims + the serialized vault.
       Proposes candidate matches. False positives here are cheap; false
       negatives just mean the claim falls through to web search in
       Phase 03, so recall is favored over precision.
    2. ``verify_matches`` — async. Independently re-checks each proposed
       match at the ``high`` tier (never downgrade — see
       docs/playbook/model-tier-selection.md), adversarially, defaulting to
       `no_vault_match` when uncertain. Appends a `RouteVerdict` per verified
       match to `claim_record.vault_verdicts` (route="vault_matched").

Read-only against the vault, same as ingest/vault_serializer.py and
ingest/alignment.py.
"""

import json
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from ingest.alignment import gather_evidence
from ingest.vault_serializer import SerializedVault, VaultNote
from utils import call_llm_with_structured_output, get_llm
from utils.claim_record import (
    CitationStatus,
    ClaimRecord,
    RouteVerdict,
)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class MatchProposal(BaseModel):
    """A single proposed claim<->note match from the batch LLM call."""

    claim_index: int = Field(description="Index into the input records list")
    note_name: str = Field(description="Name of the matched vault note")
    reasoning: str = Field(description="Why this note might support/contradict the claim")


class BatchMatchOutput(BaseModel):
    """Structured output from the batch matching LLM call."""

    matches: List[MatchProposal] = Field(description="Proposed claim-to-note matches")


class VerifyOutput(BaseModel):
    """Structured output from the per-match verification LLM call."""

    verdict: Literal["vault_supported", "vault_contradicted", "no_vault_match"] = Field(
        description="Whether the vault note supports, contradicts, or doesn't match the claim"
    )
    reasoning: str = Field(description="Why this verdict was chosen")
    supporting_note: Optional[str] = Field(
        default=None, description="Name of the note that provided the strongest evidence"
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

BATCH_MATCH_SYSTEM_PROMPT = """You match citation-free claims from a research \
draft against notes in a researcher's evidence vault.

For each numbered claim, look for vault notes that are genuinely relevant \
(they would support or contradict the claim). Only propose a match when the \
note is actually about the claim's subject — only propose matches with \
genuine relevance, since false positives waste an expensive verification \
call later.

It is fine, and expected, to leave some or all claims unmatched: any claim \
you don't propose a match for will simply be routed to web search in a \
later phase. Do not force a match.

For each match you do propose, set `claim_index` to the number the claim was \
listed under."""

BATCH_MATCH_HUMAN_PROMPT = """## Claims to match (citation-free)

{claims_block}

## Vault notes

{vault_json}"""

VERIFY_SYSTEM_PROMPT = """You are verifying a candidate claim<->vault-note match \
that was proposed by an earlier, cheaper matching pass. Be skeptical: that pass \
over-proposes on purpose, and your job is to reject anything that isn't \
genuinely supported.

Decide whether the evidence:
- vault_supported: clearly supports the claim
- vault_contradicted: clearly contradicts the claim
- no_vault_match: does not address the claim closely enough to judge either \
way, or the earlier match was simply wrong

If you are uncertain, choose no_vault_match — a false positive here is worse \
than a false negative, since a false negative just falls through to web \
search. Base your judgment strictly on the provided text. Do not use outside \
knowledge."""

VERIFY_HUMAN_PROMPT = """Claim:
{claim_text}

Candidate note: {cited_note_name} (type: {cited_note_type})
Proposed because: {proposal_reasoning}

{cited_note_content}

{linked_notes_block}"""


def _format_linked_notes(linked_notes: List) -> str:
    if not linked_notes:
        return "No linked notes."

    return "\n\n".join(
        f"Linked note: {note.name} (type: {note.note_type})\n{note.content}"
        for note in linked_notes
    )


# ---------------------------------------------------------------------------
# batch_match_claims
# ---------------------------------------------------------------------------


async def batch_match_claims(
    records: List[ClaimRecord],
    serialized_vault: SerializedVault,
) -> List[MatchProposal]:
    """Propose claim<->note matches for all citation-free claims in one call.

    Uses the ``mid`` tier (cheaper, large-context) since this is a
    high-recall triage pass — each proposal is independently re-verified at
    the ``high`` tier by `verify_matches`. Returns an empty list if there
    are no eligible claims, or if the LLM call fails.
    """
    eligible = [
        (index, record)
        for index, record in enumerate(records)
        if record.citation_status == CitationStatus.CITATION_FREE
        and record.web_verdict is not None
        and record.web_verdict.claim_text
        and record.web_verdict.claim_text.strip()
    ]

    if not eligible:
        return []

    claims_block = "\n".join(
        f'{index}: "{record.web_verdict.claim_text}"' for index, record in eligible
    )
    vault_json = json.dumps(serialized_vault.notes, default=str)

    human_prompt = BATCH_MATCH_HUMAN_PROMPT.format(
        claims_block=claims_block, vault_json=vault_json
    )

    llm = get_llm(tier="mid")

    response = await call_llm_with_structured_output(
        llm=llm,
        output_class=BatchMatchOutput,
        messages=[
            ("system", BATCH_MATCH_SYSTEM_PROMPT),
            ("human", human_prompt),
        ],
        context_desc="batch vault matching",
    )

    if response is None:
        return []

    return response.matches


# ---------------------------------------------------------------------------
# verify_matches
# ---------------------------------------------------------------------------


async def verify_matches(
    records: List[ClaimRecord],
    proposals: List[MatchProposal],
    vault_by_name: Dict[str, VaultNote],
) -> List[ClaimRecord]:
    """Independently verify each proposed match at the ``high`` tier.

    For every proposal with a valid claim index and a note that has
    gatherable evidence, appends a `RouteVerdict` (route="vault_matched") to
    the matching record's `vault_verdicts`. Proposals with an out-of-range
    index, a note not found in the vault (or with no usable content), or an
    LLM failure are silently skipped. Also copies `claim_strength` /
    `evidence_quality` from a matched CLAIM note's frontmatter when the
    verdict is `vault_supported`. Modifies and returns ``records`` in place.
    """
    llm = get_llm(tier="high")

    for proposal in proposals:
        if not (0 <= proposal.claim_index < len(records)):
            continue

        record = records[proposal.claim_index]
        if record.web_verdict is None:
            continue

        result = gather_evidence(proposal.note_name, vault_by_name)
        if result.cited_note_name is None:
            continue

        human_prompt = VERIFY_HUMAN_PROMPT.format(
            claim_text=record.web_verdict.claim_text,
            cited_note_name=result.cited_note_name,
            cited_note_type=result.cited_note_type,
            proposal_reasoning=proposal.reasoning,
            cited_note_content=result.cited_note_content,
            linked_notes_block=_format_linked_notes(result.linked_notes),
        )

        response = await call_llm_with_structured_output(
            llm=llm,
            output_class=VerifyOutput,
            messages=[
                ("system", VERIFY_SYSTEM_PROMPT),
                ("human", human_prompt),
            ],
            context_desc=f"vault match verification: claim vs {proposal.note_name}",
        )

        if response is None:
            continue

        record.vault_verdicts.append(
            RouteVerdict(
                route="vault_matched",
                verdict=response.verdict,
                reasoning=response.reasoning,
                provenance=response.supporting_note or proposal.note_name,
                provenance_type="vault_note",
            )
        )

        note = vault_by_name.get(proposal.note_name)
        if (
            note is not None
            and note.note_type == "claim"
            and response.verdict == "vault_supported"
        ):
            record.claim_strength = note.frontmatter.get("claim_strength")
            record.evidence_quality = note.frontmatter.get("evidence_quality")

    return records
