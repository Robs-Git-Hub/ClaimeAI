"""Batch triage classifier (TG 03.1).

Populates `triage_class`, `citation_expectation`, and `importance` on every
`ClaimRecord`, in one cheap (`mid` tier or below — triage is the cost
lever, never `high`) LLM call over the whole draft.

Unlike `ingest/vault_match.py`'s `batch_match_claims`, triage runs over
EVERY claim regardless of `citation_status` — TG 03.2 routing needs a
triage class on cited claims too (e.g. to decide citation expectation).

Conservative-up (Session 4 principle, Phase 03 design pillar 2): a
misclassified load-bearing claim is a silent verification miss. The prompt
instructs the model that, when uncertain between `trivial` and anything
else, it must choose the non-trivial class. Codewise, the same principle
means a claim the model omits from its response (or that the whole call
fails to produce) is left unclassified (`None` fields) rather than
defaulted to "trivial" — downstream routing treats `None` as "needs
verification", never as "skip".

`novel-result` and `dataset-dependent` exist specifically so routing (TG
03.2) can keep such claims away from web search: no web source can ever
confirm an author's own unpublished experimental result, or a claim only
checkable against a specific dataset.

See docs/playbook/claim-record-design.md for the full vocabulary.
"""

import logging
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from utils import call_llm_with_structured_output, get_llm
from utils.claim_record import ClaimRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

TriageClass = Literal[
    "trivial",
    "general-factual",
    "academic-citable",
    "dataset-dependent",
    "novel-result",
]

CitationExpectation = Literal["expected", "not-expected", "optional"]

_MIN_IMPORTANCE = 1
_MAX_IMPORTANCE = 5


class TriageProposal(BaseModel):
    """A single claim's triage classification from the batch LLM call."""

    claim_index: int = Field(description="Index into the input records list")
    triage_class: TriageClass = Field(
        description=(
            "trivial (common knowledge, needs no verification), "
            "general-factual (an ordinary factual claim), "
            "academic-citable (the kind of claim a peer reviewer would "
            "expect a citation for), "
            "dataset-dependent (verifiable ONLY against the author's own "
            "private dataset or analysis outputs, never a fact of public "
            "record -- official vote tallies, published statistics, and "
            "government/IGO records are general-factual or "
            "academic-citable, NOT dataset-dependent), "
            "novel-result (the author's own not-yet-published finding, "
            "never the open web -- if the figure is a matter of public "
            "record it is not novel-result)"
        )
    )
    citation_expectation: CitationExpectation = Field(
        description=(
            "expected (an academic citation would normally be expected here), "
            "not-expected (no citation is normally expected, e.g. trivial or "
            "the author's own result), "
            "optional (a citation would help but isn't strictly required)"
        )
    )
    importance: int = Field(
        description="How load-bearing this claim is to the draft's argument, 1 (least) to 5 (most)"
    )
    reasoning: Optional[str] = Field(
        default=None, description="Brief justification for the classification"
    )


class BatchTriageOutput(BaseModel):
    """Structured output from the batch triage LLM call."""

    classifications: List[TriageProposal] = Field(
        description="One classification per claim the model has an opinion on"
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

TRIAGE_SYSTEM_PROMPT = """You triage factual claims extracted from a research \
draft so a downstream router can send each claim to the cheapest verification \
method that can actually verify it.

Classify each numbered claim along three axes:

1. `triage_class` — one of:
   - trivial: common knowledge, needs no verification (e.g. widely known \
facts, definitions).
   - general-factual: an ordinary factual claim a web search could verify.
   - academic-citable: the kind of claim a peer reviewer would expect an \
academic citation for.
   - dataset-dependent: verifiable ONLY against the author's own private \
dataset or analysis outputs — NOT a fact of public record. Official vote \
tallies, published statistics, government or intergovernmental-organization \
(IGO) records, and anything else a search engine could reach are \
general-factual or academic-citable, never dataset-dependent, even if they \
look like a specific figure or count.
   - novel-result: the author's OWN, not-yet-published finding or result — \
new information that does not exist anywhere on the open web yet. If the \
figure is a matter of public record (something anyone else could also have \
reported), it is not novel-result.

2. `citation_expectation` — one of: expected, not-expected, optional.

3. `importance` — 1 (least load-bearing) to 5 (most load-bearing to the \
draft's argument).

Be conservative: if you are uncertain whether a claim is trivial or \
something more substantial, choose the non-trivial class. A claim wrongly \
marked trivial is never re-checked; a claim wrongly marked non-trivial just \
costs a bit more to verify.

dataset-dependent and novel-result are NEVER-WEB classes — a claim \
classified this way is routed away from web verification entirely, no \
matter what else is true about it. A missed error is the worst-case \
outcome, so it is better to send a little too much to web than too little: \
when you are uncertain between a never-web class (dataset-dependent, \
novel-result) and a web-verifiable class (general-factual, \
academic-citable), choose the web-verifiable class. Reserve \
dataset-dependent/novel-result for cases where you are confident the claim \
is genuinely unreachable by web search — the author's own unpublished \
result or a figure that exists only in a private dataset — never for facts \
of public record such as an official vote count, a published statistic, or \
a government/IGO report, even one you personally cannot look up right now.

It is fine to leave a claim out of your response entirely if you have no \
confident opinion on it — an omitted claim is treated conservatively \
downstream (as needing full verification), so do not force a classification \
you aren't confident about.

For each claim you do classify, set `claim_index` to the number the claim \
was listed under."""

TRIAGE_HUMAN_PROMPT = """## Claims to triage

{claims_block}"""


# ---------------------------------------------------------------------------
# triage_claims
# ---------------------------------------------------------------------------


def _clamp_importance(value: int) -> int:
    return max(_MIN_IMPORTANCE, min(_MAX_IMPORTANCE, value))


async def triage_claims(records: List[ClaimRecord]) -> List[ClaimRecord]:
    """Classify every claim in one batch LLM call, in place.

    Populates `triage_class`, `citation_expectation`, and `importance` on
    each `ClaimRecord`. Never touches `claim_strength` / `evidence_quality`
    (vault-derived fields from Phase 02).

    Runs over ALL claims regardless of `citation_status` — this differs
    from `ingest/vault_match.py`'s `batch_match_claims`, which only
    considers citation-free claims.

    No-op (returns `records` unchanged) if there are no claims with
    extractable claim text, or if the LLM call fails. Proposals with an
    out-of-range `claim_index` are silently ignored. Claims the model
    omits from its response are left unclassified (`None`), never
    defaulted to "trivial" — this is the conservative-up behavior the
    phase requires. Modifies and returns `records` in place, matching
    `verify_matches`'s convention.
    """
    eligible = [
        (index, record)
        for index, record in enumerate(records)
        if record.claim_text and record.claim_text.strip()
    ]

    if not eligible:
        return records

    claims_block = "\n".join(
        f'{index}: "{record.claim_text}"' for index, record in eligible
    )
    human_prompt = TRIAGE_HUMAN_PROMPT.format(claims_block=claims_block)

    llm = get_llm(tier="mid")

    response = await call_llm_with_structured_output(
        llm=llm,
        output_class=BatchTriageOutput,
        messages=[
            ("system", TRIAGE_SYSTEM_PROMPT),
            ("human", human_prompt),
        ],
        context_desc="batch claim triage",
    )

    if response is None:
        logger.info("Triage LLM call failed; all claims remain unclassified.")
        return records

    for proposal in response.classifications:
        if not (0 <= proposal.claim_index < len(records)):
            continue

        record = records[proposal.claim_index]
        record.triage_class = proposal.triage_class
        record.citation_expectation = proposal.citation_expectation
        record.importance = _clamp_importance(proposal.importance)

    return records
