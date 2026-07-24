"""Evidence summarization for the claim verifier evidence path (TG 03.4).

Before the high-tier ``evaluate_evidence`` node judges a claim, this module
condenses raw retrieved evidence into claim-relevant extracts using a
cheaper model. Session 3 cost data showed Exa returns ~30KB and Tavily up
to ~1.1MB of raw evidence per run; Session 4 cost analysis found 76% of
per-paper pipeline spend sat in the high tier, largely input tokens. This
step cuts that input before it reaches the expensive evaluator.

Placement decision: a **pre-processing step called from within**
``evaluate_evidence_node`` (see claim_verifier/nodes/evaluate_evidence.py),
not a separate LangGraph node. ``ClaimVerifierState.evidence`` is declared
``Annotated[List[Evidence], add]`` — LangGraph reducers combine a node's
partial state update with the existing value using that reducer, so a
"summarize_evidence" node returning a condensed evidence list would be
concatenated onto (not substituted for) the raw evidence accumulated
across search iterations, doubling it rather than replacing it. Calling
the summarizer inline, right before the evaluation prompt is built, avoids
that pitfall entirely: the condensed set only ever exists as a local
variable, evaluate_evidence still reads exactly one evidence set
(summarized when the switch is on, raw when it's off), and the change is
confined to the evidence path without touching agent.py's graph wiring or
the state schema. ``evaluate_evidence`` stays at tier "high" and is the
only place that renders a verdict — this module only changes what it reads.

Tier choice: **mid**, not low. Per docs/playbook/model-tier-selection.md,
low tier is reserved for high-volume, mechanical structured extraction
(keep/discard, pronoun resolution) that doesn't require judgment.
Summarization is judgment-sensitive: the model must recognize which
sentences support vs. refute the claim and preserve both with equal
fidelity, or it silently turns "Refuted" verdicts into "Supported" ones
downstream (the "summarization bias" risk named in the Phase 03 plan).
Mid tier is already used in this package for comparable reasoning-adjacent
tasks (search query generation, search-sufficiency decisions) at a
fraction of high-tier cost - the right cost/fidelity trade-off here too.

Reusability: ``summarize_evidence_for_claim`` takes claim text and a list
of ``Evidence`` items and returns a condensed list of ``Evidence`` items —
nothing web-specific. The web route (evaluate_evidence_node) is a thin
caller of it today; Phase 04's corpus route can call the same function
over retrieved passages without changes here.

Failure handling: any failure (LLM construction error, LLM call error,
malformed/empty structured output) falls back to the original, unsummarized
evidence. A claim is never dropped and verification never crashes because
summarization failed - see the constraints in the Phase 03 plan.

Source attribution: extracts are matched back to their original
``Evidence`` item by 1-based source index (mirroring the existing
``influential_source_indices`` pattern in evaluate_evidence.py). The URL
and title on every returned ``Evidence`` always come from the original
item, never from the model's output, so a hallucinated or mis-quoted URL
from the summarizer cannot corrupt provenance. Any source the model omits
from its extracts falls back to that source's full raw text rather than
being dropped, so a summarizer that skips a source (e.g. one that only
contains refuting content) still leaves that source's raw content
available to the evaluator instead of silently vanishing.
"""

import logging
from typing import List

from pydantic import BaseModel, Field

from claim_verifier.config import EVIDENCE_SUMMARIZATION_CONFIG
from claim_verifier.prompts import (
    EVIDENCE_SUMMARIZATION_HUMAN_PROMPT,
    EVIDENCE_SUMMARIZATION_SYSTEM_PROMPT,
)
from claim_verifier.schemas import Evidence
from utils import call_llm_with_structured_output, estimate_token_count, get_llm

logger = logging.getLogger(__name__)


class ClaimRelevantExtract(BaseModel):
    """One condensed, claim-relevant extract tied back to its source index."""

    source_index: int = Field(
        description=(
            "1-based index of the source this extract summarizes, matching "
            "the order of the input evidence list."
        )
    )
    extract: str = Field(
        description=(
            "Condensed claim-relevant text from this source. Must preserve "
            "any content that supports OR refutes/contradicts the claim "
            "with equal fidelity - never omit or soften contradicting "
            "evidence relative to supporting evidence."
        )
    )


class EvidenceSummaryOutput(BaseModel):
    """Structured output for a single evidence-summarization call."""

    extracts: List[ClaimRelevantExtract] = Field(
        default_factory=list,
        description=(
            "One extract per input source. Every source must be "
            "represented, including sources that only contain evidence "
            "contradicting the claim."
        ),
    )


def _format_sources_for_prompt(evidence_items: List[Evidence]) -> str:
    return "\n\n".join(
        f"Source {i + 1}: {item.url}\n"
        + (f"Title: {item.title}\n" if item.title else "")
        + f"Text: {item.text.strip()}\n---"
        for i, item in enumerate(evidence_items)
    )


async def summarize_evidence_for_claim(
    claim_text: str, evidence_items: List[Evidence]
) -> List[Evidence]:
    """Condense a claim's raw evidence set into claim-relevant extracts.

    Makes exactly one LLM call total for the whole evidence set (never one
    call per search result). Returns ``evidence_items`` unchanged when:
    summarization is disabled via config, there is no evidence to
    summarize, or the summarization call fails for any reason.

    Args:
        claim_text: The claim the evidence is being gathered for.
        evidence_items: Raw evidence items (e.g. web search results, or in
            future a corpus route's retrieved passages).

    Returns:
        A list of ``Evidence`` items the same length as ``evidence_items``,
        with ``text`` condensed to claim-relevant content where the model
        provided an extract, and the original ``text`` preserved for any
        source the model didn't cover. ``url``, ``title``, and
        ``is_influential`` always come from the original item.
    """
    if not evidence_items:
        return evidence_items

    if not EVIDENCE_SUMMARIZATION_CONFIG.get("enabled", True):
        return evidence_items

    raw_text = "\n".join(item.text for item in evidence_items)
    raw_chars = len(raw_text)

    try:
        llm = get_llm(tier=EVIDENCE_SUMMARIZATION_CONFIG.get("tier", "mid"))
    except Exception as e:
        logger.error(
            f"Failed to construct evidence summarization LLM for claim "
            f"'{claim_text}': {e}. Falling back to raw evidence "
            f"({len(evidence_items)} items)."
        )
        return evidence_items

    messages = [
        ("system", EVIDENCE_SUMMARIZATION_SYSTEM_PROMPT),
        (
            "human",
            EVIDENCE_SUMMARIZATION_HUMAN_PROMPT.format(
                claim_text=claim_text,
                sources=_format_sources_for_prompt(evidence_items),
            ),
        ),
    ]

    response = await call_llm_with_structured_output(
        llm=llm,
        output_class=EvidenceSummaryOutput,
        messages=messages,
        context_desc=f"evidence summarization for claim '{claim_text}'",
    )

    if not response or not response.extracts:
        logger.warning(
            f"Evidence summarization failed or returned no extracts for "
            f"claim '{claim_text}'; falling back to raw evidence "
            f"({len(evidence_items)} items)."
        )
        return evidence_items

    extracts_by_index = {
        e.source_index: e.extract
        for e in response.extracts
        if 1 <= e.source_index <= len(evidence_items)
    }

    summarized = [
        Evidence(
            url=item.url,
            title=item.title,
            text=extracts_by_index.get(i, item.text),
            is_influential=item.is_influential,
        )
        for i, item in enumerate(evidence_items, start=1)
    ]

    summarized_text = "\n".join(item.text for item in summarized)
    summarized_chars = len(summarized_text)
    reduction_pct = (1 - summarized_chars / raw_chars) * 100 if raw_chars else 0.0

    logger.info(
        "evidence_summarization: claim=%r sources=%d raw_chars=%d "
        "summarized_chars=%d raw_tokens_est=%d summarized_tokens_est=%d "
        "reduction=%.1f%%",
        claim_text,
        len(evidence_items),
        raw_chars,
        summarized_chars,
        estimate_token_count(raw_text),
        estimate_token_count(summarized_text),
        reduction_pct,
    )

    return summarized
