"""Citation-free vault matching (TG 02.5).

For claims WITHOUT a wikilink citation (`CitationStatus.CITATION_FREE`),
propose candidate claim<->note matches against the vault in bulk (one cheap
LLM call), then verify each proposed match independently and expensively.

Two-step design, mirroring `ingest/alignment.py`'s two-step shape:
    1. ``batch_match_claims`` — one LLM call (``mid`` tier — cheaper, large
       context) with ALL citation-free claims + the serialized vault.
       Proposes candidate matches. False positives here are cheap; false
       negatives just mean the claim falls through to web search in
       Phase 03, so recall is favored over precision. Matches are proposed
       for notes that CONTRADICT a claim just as readily as notes that
       support it -- a different number/date/name for the same assertion
       is a match, not a miss; `verify_matches` decides the verdict.
    2. ``verify_matches`` — async. Independently re-checks each proposed
       match at the ``high`` tier (never downgrade — see
       docs/playbook/model-tier-selection.md), adversarially, defaulting to
       `no_vault_match` when uncertain. Appends a `RouteVerdict` per verified
       match to `claim_record.route_verdicts` (route="vault_matched").

Full-vault fallback (Phase 03 milestone review). The batch matcher's normal
corpus is filtered by ``argument_pyramid`` -- notes that support this paper
but were never tagged into its pyramid are invisible to it, and a real
matching claim can be missed entirely. ``batch_match_claims_fallback`` is a
SECOND one-call batch pass (never one call per claim) over a wider corpus --
the full vault filtered by evidence TYPES only (no ``argument_pyramid``
filter) -- restricted to claims the filtered pass left unmatched. Unlike
pass 1, this call runs at the ``high`` tier: it is exactly one call per run
covering every still-unmatched claim, so the cost of the smarter model is
negligible, and the milestone review showed the ``mid`` tier missing a
same-subject-different-number match ("98 votes" claim vs. a "93 votes" vault
note) in a 353-note corpus that the ``high`` tier catches. It also builds a
free, code-only "priority candidates" hint (`extract_claim_keywords` /
`_find_priority_candidates`) -- notes containing a number or proper noun
from an unmatched claim are named explicitly in the prompt, drawing the
model's attention to them without limiting it to only those notes. Its
proposals flow through the same ``verify_matches`` high-tier check, tagged
``provenance_type="vault_note_fallback"`` so the gap report (see
``ingest/gap_report.py``) can tell the vault owner exactly which notes are
missing the tag. Gated by ``config.toml``'s ``pipeline.vault_match_fallback``
(default on) via ``VAULT_MATCH_FALLBACK_ENABLED``; orchestration (see
``scripts/run_heavy.py``) decides when to call it.

Read-only against the vault, same as ingest/vault_serializer.py and
ingest/alignment.py.
"""

import asyncio
import json
import logging
import re
from typing import Dict, List, Literal, Optional, Set

from pydantic import BaseModel, Field

from ingest.alignment import gather_evidence
from ingest.vault_serializer import SerializedVault, VaultNote, serialize_vault
from utils import call_llm_with_structured_output, get_llm
from utils.claim_record import (
    CitationStatus,
    ClaimRecord,
    RouteVerdict,
    VaultVerdict,
)
from utils.config import config as _config

logger = logging.getLogger(__name__)

_PIPELINE_CONFIG = _config.get("pipeline", {})

# Bounds how many high-tier verification calls run concurrently. A
# module-level implementation detail, not a user-facing knob (see TG 03.5).
MAX_CONCURRENT_LLM = 5

# Off = current single-pass behavior (filtered-corpus matching only).
VAULT_MATCH_FALLBACK_ENABLED: bool = _PIPELINE_CONFIG.get("vault_match_fallback", True)

# Conservative budget for the full-vault fallback corpus. If the serialized
# full vault exceeds this, `serialize_vault` records a warning (logged below)
# and the call proceeds anyway -- chunked matching remains a documented
# future fallback, not implemented here.
FALLBACK_TOKEN_BUDGET = 200_000

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

Propose matches for notes that CONTRADICT a claim just as readily as notes \
that support it. A note is a match whenever it addresses the same factual \
assertion as the claim, even if it gives a different number, date, or name \
for it — a contradiction match is just as important as a supporting match, \
since the verification pass (not you) determines the final verdict. For \
example, a claim stating "98 votes" and a note stating "93 votes for the \
same resolution" is a match, not a miss.

It is fine, and expected, to leave some or all claims unmatched: any claim \
you don't propose a match for will simply be routed to web search in a \
later phase. Do not force a match.

For each match you do propose, set `claim_index` to the number the claim was \
listed under."""

BATCH_MATCH_HUMAN_PROMPT = """## Claims to match (citation-free)

{claims_block}

## Vault notes

Propose a match whenever a note addresses the same factual assertion as a \
claim — whether it supports the claim or contradicts it (e.g. a different \
number, date, or name for the same thing). Over-proposing is preferable to \
missing a real match; the verification pass will sort out the verdict.

{vault_json}{priority_candidates_section}"""

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


# ---------------------------------------------------------------------------
# Keyword extraction (free recall boost for the fallback pass)
# ---------------------------------------------------------------------------

# Numbers (with internal commas/decimals/slashes/hyphens, e.g. "1,024",
# "98.6", "1990s").
_KEYWORD_NUMBER_RE = re.compile(r"\d[\d,.\-/]*")

# Capitalized proper-noun-ish tokens and codes: "Ukraine", "UN", "ES-11/7".
# The continuation group also allows "/" so multi-segment resolution/case
# codes match in full, not just their first segment.
_KEYWORD_PROPER_NOUN_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:[-/][A-Za-z0-9]+)*\b")

# Common sentence-initial capitals that carry no identifying signal on their
# own -- excluded so they don't drown out real keywords in the candidate list.
_KEYWORD_STOPWORDS = {
    "The", "A", "An", "This", "That", "These", "Those", "It", "Its",
    "In", "On", "At", "For", "With", "As", "Of", "To", "By", "From",
    "And", "But", "Or", "If", "Is", "Was", "Are", "Were",
}


def extract_claim_keywords(claim_text: str) -> Set[str]:
    """Pull numbers and capitalized proper nouns/acronyms out of ``claim_text``.

    Pure string/regex, no LLM call -- used to build a "priority candidates"
    hint for the full-vault fallback pass (see `batch_match_claims_fallback`)
    so the model's attention is drawn to notes containing the same numbers
    or names even in a large corpus, without replacing the model's own
    judgment (it still sees every note).

    Returns an empty set for empty/whitespace-only input.
    """
    if not claim_text or not claim_text.strip():
        return set()

    keywords: Set[str] = set(_KEYWORD_NUMBER_RE.findall(claim_text))

    for match in _KEYWORD_PROPER_NOUN_RE.finditer(claim_text):
        word = match.group(0)
        if word in _KEYWORD_STOPWORDS:
            continue
        keywords.add(word)

    return keywords


def _find_priority_candidates(
    records: List[ClaimRecord],
    notes: List[VaultNote],
) -> Dict[str, Set[str]]:
    """Map note name -> keywords (from ``records``) found in that note's text.

    Pure string containment against each note's serialized fields (name,
    frontmatter, body sections, wikilinks) -- no LLM call. Notes with no
    matched keyword are omitted entirely.
    """
    candidates: Dict[str, Set[str]] = {}

    for record in records:
        keywords = extract_claim_keywords(record.claim_text or "")
        if not keywords:
            continue

        for note in notes:
            haystack = json.dumps(
                {
                    "name": note.name,
                    "frontmatter": note.frontmatter,
                    "sections": note.body_sections,
                    "wikilinks": note.wikilinks,
                },
                default=str,
            )
            matched = {kw for kw in keywords if kw in haystack}
            if matched:
                candidates.setdefault(note.name, set()).update(matched)

    return candidates


def _format_priority_candidates_section(candidates: Dict[str, Set[str]]) -> str:
    """Render `_find_priority_candidates` output as a human-prompt section.

    Empty string when there are no candidates, so callers can always splice
    this into `BATCH_MATCH_HUMAN_PROMPT`'s `priority_candidates_section` slot
    without an extra conditional.
    """
    if not candidates:
        return ""

    lines = "\n".join(
        f"- {name} (matched terms: {', '.join(sorted(terms))})"
        for name, terms in sorted(candidates.items())
    )
    return (
        "\n\n## Priority candidates\n\n"
        "These notes contain terms (numbers, names, codes) that also appear "
        "in one or more of the claims listed above. They are worth a close "
        "look, but are not the only eligible notes -- any note in the corpus "
        "above may still be a genuine match.\n\n"
        f"{lines}"
    )


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
    exclude_indices: Optional[Set[int]] = None,
    tier: str = "mid",
    priority_candidates: Optional[Dict[str, Set[str]]] = None,
) -> List[MatchProposal]:
    """Propose claim<->note matches for all citation-free claims in one call.

    Defaults to the ``mid`` tier (cheaper, large-context) since this is a
    high-recall triage pass — each proposal is independently re-verified at
    the ``high`` tier by `verify_matches`. Returns an empty list if there
    are no eligible claims, or if the LLM call fails.

    ``exclude_indices``, when given, drops those record indices from
    eligibility even if they'd otherwise qualify -- used by
    `batch_match_claims_fallback` to scope the full-vault fallback pass to
    claims the filtered pass left unmatched.

    ``tier`` lets `batch_match_claims_fallback` promote its single call to
    ``high`` (this pass 1 caller stays on the ``mid`` default).

    ``priority_candidates``, when given, is a note-name -> matched-keywords
    map (see `_find_priority_candidates`) rendered into a "Priority
    candidates" section appended to the human prompt -- a free, code-only
    recall boost that draws the model's attention to notes sharing numbers
    or names with an unmatched claim, without restricting it to only those
    notes.
    """
    eligible = [
        (index, record)
        for index, record in enumerate(records)
        if record.citation_status == CitationStatus.CITATION_FREE
        and record.claim_text
        and record.claim_text.strip()
        and (exclude_indices is None or index not in exclude_indices)
    ]

    if not eligible:
        return []

    claims_block = "\n".join(
        f'{index}: "{record.claim_text}"' for index, record in eligible
    )
    vault_json = json.dumps(serialized_vault.notes, default=str)
    priority_candidates_section = _format_priority_candidates_section(
        priority_candidates or {}
    )

    human_prompt = BATCH_MATCH_HUMAN_PROMPT.format(
        claims_block=claims_block,
        vault_json=vault_json,
        priority_candidates_section=priority_candidates_section,
    )

    llm = get_llm(tier=tier)

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
# Full-vault fallback (Phase 03 milestone review)
# ---------------------------------------------------------------------------


def matched_citation_free_indices(records: List[ClaimRecord]) -> Set[int]:
    """Indices with a confirmed ``vault_matched`` verdict (not ``no_vault_match``).

    Pure, synchronous. Used to scope `batch_match_claims_fallback` to claims
    the filtered pass left unmatched -- either no proposal was made for them
    at all, or the proposal `verify_matches` received was rejected.
    """
    matched: Set[int] = set()
    for index, record in enumerate(records):
        for rv in record.route_verdicts:
            if rv.route == "vault_matched" and rv.verdict != VaultVerdict.NO_VAULT_MATCH.value:
                matched.add(index)
                break
    return matched


async def batch_match_claims_fallback(
    records: List[ClaimRecord],
    full_notes: List[VaultNote],
    already_matched_indices: Set[int],
) -> List[MatchProposal]:
    """Second batch-match pass over the full (type-filtered-only) vault.

    Same one-call batch-propose shape as `batch_match_claims` -- ONE LLM
    call covering every still-unmatched claim, never one call per claim --
    just a wider corpus (``full_notes``, typically the vault filtered by
    `ingest.vault_serializer.DEFAULT_EVIDENCE_TYPES` only, with no
    ``argument_pyramid`` filter) and a narrower claim set (everything except
    ``already_matched_indices``).

    Runs at the ``high`` tier (never ``mid``, unlike pass 1): this is a
    SINGLE call covering all still-unmatched claims for the whole run, so
    the cost of the smarter model is negligible next to the recall it buys
    in a large corpus -- see the milestone-review "98 vs 93 votes" miss that
    motivated this (a reasoning task the mid-tier model got wrong).

    Also computes a free, code-only "priority candidates" hint (see
    `_find_priority_candidates` / `extract_claim_keywords`): notes whose
    text contains a number or proper noun from an unmatched claim are
    surfaced to the model by name, drawing its attention to them even in a
    353-note corpus, without restricting it to only those notes.

    A claim matched here means the matching note exists in the vault but
    lacks the ``argument_pyramid`` tag for this paper -- callers should pass
    ``provenance_type="vault_note_fallback"`` to `verify_matches` for these
    proposals so the gap report can surface the tagging gap.

    Logs the fallback corpus size/token estimate, and any budget warnings
    from `serialize_vault` (see `FALLBACK_TOKEN_BUDGET`) -- exceeding the
    budget only logs a warning and proceeds; chunked matching remains a
    documented future fallback, not implemented here.
    """
    full_serialized = serialize_vault(full_notes, token_budget=FALLBACK_TOKEN_BUDGET)
    logger.info(
        "Full-vault fallback corpus: %d notes, ~%d tokens",
        full_serialized.note_count,
        full_serialized.token_estimate,
    )
    for warning in full_serialized.warnings:
        logger.warning("Full-vault fallback: %s", warning)

    unmatched_records = [
        record
        for index, record in enumerate(records)
        if index not in already_matched_indices
        and record.citation_status == CitationStatus.CITATION_FREE
        and record.claim_text
        and record.claim_text.strip()
    ]
    priority_candidates = _find_priority_candidates(unmatched_records, full_notes)

    return await batch_match_claims(
        records,
        full_serialized,
        exclude_indices=already_matched_indices,
        tier="high",
        priority_candidates=priority_candidates,
    )


# ---------------------------------------------------------------------------
# verify_matches
# ---------------------------------------------------------------------------


async def verify_matches(
    records: List[ClaimRecord],
    proposals: List[MatchProposal],
    vault_by_name: Dict[str, VaultNote],
    provenance_type: str = "vault_note",
) -> List[ClaimRecord]:
    """Independently verify each proposed match at the ``high`` tier.

    For every proposal with a valid claim index and a note that has
    gatherable evidence, appends a `RouteVerdict` (route="vault_matched") to
    the matching record's `route_verdicts`. Proposals with an out-of-range
    index, a note not found in the vault (or with no usable content), or an
    LLM failure are silently skipped. Also copies `claim_strength` /
    `evidence_quality` from a matched CLAIM note's frontmatter when the
    verdict is `vault_supported`. Modifies and returns ``records`` in place.

    ``provenance_type`` is stamped onto each appended `RouteVerdict` (default
    ``"vault_note"``, the pre-existing value). Callers verifying full-vault
    fallback proposals pass ``"vault_note_fallback"`` so the gap report can
    tell filtered-corpus matches apart from fallback matches (a vault
    tagging gap -- see `ingest/gap_report.py`).

    Each proposal's verification is independent (the batch matcher never
    proposes more than one match per claim index, so distinct proposals
    always write to distinct records -- no shared-state race), so all
    proposals are verified concurrently, bounded by `MAX_CONCURRENT_LLM` to
    avoid an unbounded burst of high-tier LLM calls.
    """
    llm = get_llm(tier="high")
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM)

    async def _verify_one(proposal: MatchProposal) -> None:
        if not (0 <= proposal.claim_index < len(records)):
            return

        record = records[proposal.claim_index]
        if record.claim_text is None:
            return

        result = gather_evidence(proposal.note_name, vault_by_name)
        if result.cited_note_name is None:
            return

        human_prompt = VERIFY_HUMAN_PROMPT.format(
            claim_text=record.claim_text,
            cited_note_name=result.cited_note_name,
            cited_note_type=result.cited_note_type,
            proposal_reasoning=proposal.reasoning,
            cited_note_content=result.cited_note_content,
            linked_notes_block=_format_linked_notes(result.linked_notes),
        )

        async with semaphore:
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
            return

        record.route_verdicts.append(
            RouteVerdict(
                route="vault_matched",
                verdict=response.verdict,
                reasoning=response.reasoning,
                provenance=response.supporting_note or proposal.note_name,
                provenance_type=provenance_type,
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

    await asyncio.gather(*[_verify_one(proposal) for proposal in proposals])

    return records


# ---------------------------------------------------------------------------
# supersede_stale_no_match
# ---------------------------------------------------------------------------


def supersede_stale_no_match(records: List[ClaimRecord]) -> List[ClaimRecord]:
    """Drop stale ``no_vault_match`` verdicts once a real finding supersedes them.

    A ``no_vault_match`` verdict on route="vault_matched" is a status ("we
    checked and found nothing"), not evidence. When a later pass -- e.g. the
    full-vault fallback, run after pass 1 already rejected a proposal --
    appends a real finding (``vault_supported`` / ``vault_contradicted``) on
    that same route, the earlier absence verdict is superseded and must be
    removed: leaving both would render the report as contradicting itself
    (an explicit "no match" next to a positive/negative finding for the same
    claim). A lone ``no_vault_match`` with no finding is left untouched, as
    are verdicts on any other route.

    Pure, synchronous. Call after the fallback `verify_matches` pass (not
    inside `verify_matches` itself -- pass 1 must still record rejections
    normally in case no fallback ever runs). Modifies and returns ``records``
    in place.
    """
    for record in records:
        has_finding = any(
            rv.route == "vault_matched" and rv.verdict != VaultVerdict.NO_VAULT_MATCH.value
            for rv in record.route_verdicts
        )
        if not has_finding:
            continue
        record.route_verdicts = [
            rv
            for rv in record.route_verdicts
            if not (
                rv.route == "vault_matched"
                and rv.verdict == VaultVerdict.NO_VAULT_MATCH.value
            )
        ]

    return records
