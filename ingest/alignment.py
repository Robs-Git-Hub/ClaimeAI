"""Cited-claim alignment (TG 02.4).

For claims with a parseable vault citation (`CitationStatus.CITED`), decide
whether the cited vault note (and its one-hop wikilinks) actually supports
the claim text. This is separate from web verification: it checks that an
author's citation is honest, not that the claim is true.

Two-step design:
    1. ``gather_evidence`` — pure, synchronous evidence collection. No LLM
       calls. Looks up the cited note and follows its wikilinks exactly one
       hop (no deeper traversal).
    2. ``evaluate_alignment`` — async. Calls the LLM (at the ``high`` tier;
       never downgrade — see docs/playbook/model-tier-selection.md) once per
       cited note that has evidence, and appends a `RouteVerdict` per note
       to `claim_record.vault_verdicts`.

Read-only against the vault, same as ingest/vault_serializer.py.
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from ingest.vault_serializer import VaultNote
from utils import call_llm_with_structured_output, get_llm
from utils.claim_record import (
    CitationStatus,
    ClaimRecord,
    RouteVerdict,
    VaultVerdict,
)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class LinkedNoteEvidence(BaseModel):
    """One-hop wikilink evidence gathered alongside a cited note."""

    name: str
    note_type: str
    content: str = Field(description="Concatenated body_sections text")


class GatherResult(BaseModel):
    """Evidence bundle for a single cited note, or a reason there is none.

    When ``cited_note_name`` is None, ``verdict`` holds the ``VaultVerdict``
    value to record directly (no LLM call needed). Otherwise the evidence
    fields are populated for the LLM alignment call.
    """

    verdict: Optional[str] = None
    cited_note_name: Optional[str] = None
    cited_note_type: Optional[str] = None
    cited_note_content: Optional[str] = None
    linked_notes: List[LinkedNoteEvidence] = Field(default_factory=list)


class AlignmentOutput(BaseModel):
    """Structured LLM output for a single claim-vs-note alignment check."""

    verdict: Literal["vault_supported", "vault_contradicted", "not_supported"] = Field(
        description="Whether the vault evidence supports, contradicts, or fails to support the claim"
    )
    reasoning: str = Field(
        description="Why the evidence does or doesn't support the claim"
    )
    supporting_note: Optional[str] = Field(
        default=None,
        description="Name of the note that provided the strongest evidence",
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ALIGNMENT_SYSTEM_PROMPT = """You check whether a citation in a research draft is honest.

You will be given a claim sentence and the vault note(s) it cites as
evidence, including notes one hop away that the cited note links to.

Decide whether the evidence:
- vault_supported: clearly supports the claim
- vault_contradicted: clearly contradicts the claim
- not_supported: does not address the claim closely enough to judge either
  way (e.g. the citation is a miscite, or the note is about something else)

Base your judgment strictly on the provided text. Do not use outside
knowledge. Choose exactly one verdict."""

ALIGNMENT_HUMAN_PROMPT = """Claim:
{claim_text}

Cited note: {cited_note_name} (type: {cited_note_type})
{cited_note_content}

{linked_notes_block}"""


def _format_linked_notes(linked_notes: List[LinkedNoteEvidence]) -> str:
    if not linked_notes:
        return "No linked notes."

    return "\n\n".join(
        f"Linked note: {note.name} (type: {note.note_type})\n{note.content}"
        for note in linked_notes
    )


# ---------------------------------------------------------------------------
# gather_evidence — pure, synchronous
# ---------------------------------------------------------------------------


def _concat_body(note: VaultNote) -> str:
    """Concatenate all body_sections values into one evidence string."""
    return "\n\n".join(note.body_sections.values())


def gather_evidence(
    note_name: str, vault_by_name: Dict[str, VaultNote]
) -> GatherResult:
    """Gather a cited note's content plus its one-hop wikilinked notes.

    Does not call an LLM. Follows wikilinks exactly one hop — a linked
    note's own wikilinks are never traversed.
    """
    note = vault_by_name.get(note_name)
    if note is None:
        return GatherResult(verdict=VaultVerdict.NOTE_NOT_IN_VAULT.value)

    cited_content = _concat_body(note)

    linked_notes: List[LinkedNoteEvidence] = []
    for linked_name in note.wikilinks:
        linked_note = vault_by_name.get(linked_name)
        if linked_note is None:
            continue
        linked_notes.append(
            LinkedNoteEvidence(
                name=linked_note.name,
                note_type=linked_note.note_type,
                content=_concat_body(linked_note),
            )
        )

    has_cited_content = bool(cited_content.strip())
    has_linked_content = any(ln.content.strip() for ln in linked_notes)
    if not has_cited_content and not has_linked_content:
        return GatherResult(verdict=VaultVerdict.INSUFFICIENT_VAULT_CONTENT.value)

    return GatherResult(
        found=True,
        cited_note_name=note.name,
        cited_note_type=note.note_type,
        cited_note_content=cited_content,
        linked_notes=linked_notes,
    )


# ---------------------------------------------------------------------------
# evaluate_alignment — async, calls the LLM
# ---------------------------------------------------------------------------


async def evaluate_alignment(
    claim_record: ClaimRecord,
    vault_by_name: Dict[str, VaultNote],
    full_vault_by_name: Optional[Dict[str, VaultNote]] = None,
) -> ClaimRecord:
    """Evaluate each cited note in ``claim_record.cite_set`` against its text.

    Appends one `RouteVerdict` per cited note to `claim_record.vault_verdicts`
    (route="vault_aligned"). No-ops (returns unchanged) if the claim is not
    cited, has an empty cite set, or has no web_verdict to source claim text
    from. If the LLM call fails (returns None), that note is silently
    skipped — no verdict is appended for it.

    ``full_vault_by_name``, when provided, is an unfiltered vault index used
    as a fallback for cited notes not found in the (possibly argument-pyramid-
    filtered) ``vault_by_name``.  This prevents false ``note_not_in_vault``
    verdicts for notes that exist in the vault but weren't included in the
    filtered subset.
    """
    if claim_record.citation_status != CitationStatus.CITED or not claim_record.cite_set:
        return claim_record

    if claim_record.web_verdict is None:
        return claim_record

    claim_text = claim_record.web_verdict.claim_text
    if not claim_text or not claim_text.strip():
        return claim_record

    llm = get_llm(tier="high")

    for note_name in claim_record.cite_set:
        result = gather_evidence(note_name, vault_by_name)
        if result.cited_note_name is None and full_vault_by_name is not None:
            result = gather_evidence(note_name, full_vault_by_name)

        if result.cited_note_name is None:
            claim_record.vault_verdicts.append(
                RouteVerdict(
                    route="vault_aligned",
                    verdict=result.verdict,
                    reasoning=None,
                    provenance=note_name,
                    provenance_type=None,
                )
            )
            continue

        human_prompt = ALIGNMENT_HUMAN_PROMPT.format(
            claim_text=claim_text,
            cited_note_name=result.cited_note_name,
            cited_note_type=result.cited_note_type,
            cited_note_content=result.cited_note_content,
            linked_notes_block=_format_linked_notes(result.linked_notes),
        )

        response = await call_llm_with_structured_output(
            llm=llm,
            output_class=AlignmentOutput,
            messages=[
                ("system", ALIGNMENT_SYSTEM_PROMPT),
                ("human", human_prompt),
            ],
            context_desc=f"vault alignment: claim vs {note_name}",
        )

        if response is None:
            continue

        claim_record.vault_verdicts.append(
            RouteVerdict(
                route="vault_aligned",
                verdict=response.verdict,
                reasoning=response.reasoning,
                provenance=response.supporting_note or note_name,
                provenance_type="vault_note",
            )
        )

    return claim_record
