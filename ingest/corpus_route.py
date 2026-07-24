"""Corpus route: verify a claim against the author's own paper corpus (TG 04.3).

Registers `"corpus"` as a real verification route for claims the routing
policy keeps away from web search (triage classes `novel-result` and
`dataset-dependent`, see `ingest/routing.py`'s `never-web` policy row) but
that the author's own ingested paper corpus (doc-rag-backend,
`ingest/corpus_client.py`) may still be able to confirm or contradict.

Pipeline, mirroring the web route's search -> summarize -> evaluate shape:
    1. `search_corpus` (`ingest/corpus_client.py`) -- hybrid/dense/fts search
       scoped to the manifest's `corpus_ids`. Returns `None` on any failure
       (network error, non-2xx, bad body) -- a soft failure, not a pipeline
       abort.
    2. `_wrap_evidence` -- wraps each returned chunk as a `claim_verifier`
       `Evidence` item (`url="corpus://<document_id>#<chunk_id>"`, `text`
       including the chunk's `context` enrichment, `title` from the
       document).
    3. `summarize_evidence_for_claim` (`claim_verifier/evidence_summarization.py`,
       mid tier, config-gated by `summarize_evidence`) -- condenses the
       wrapped evidence exactly once, reused unmodified from the web route's
       evidence path (it was already written to be evidence-source-agnostic
       -- see that module's "Reusability" note).
    4. `_evaluate_corpus_evidence` -- a route-local high-tier evaluation
       call (`get_llm(tier="high")` + `with_structured_output`, following
       the house style of `ingest/alignment.py:evaluate_alignment`). This is
       NOT a call into `claim_verifier.nodes.evaluate_evidence` --
       that node's structured-output verdict field is typed
       `claim_verifier.schemas.VerificationResult`, whose *actual* enum
       values are only `Supported`/`Refuted` (see that file: `Insufficient
       Information` is commented out of the enum even though the prompt
       still describes it). The corpus route's fixed vocabulary requires a
       `corpus_insufficient` verdict, which `VerificationResult` structurally
       cannot represent without editing `claim_verifier/schemas.py` --
       out of scope this phase (compose, don't modify). Writing a small
       route-local evaluator sidesteps that without touching
       `claim_verifier` internals. The evaluation call happens exactly once
       per claim, at "high" tier -- never downgraded, per house policy.

Manifest scoping (design decision, TG 04.3): `RouteHandler` (the protocol in
`ingest/routing.py`) is `async (record) -> Optional[RouteVerdict]` -- it has
no way to receive `manifest.corpus_ids` directly, and `execute_routing`'s
signature must not change to thread it through. This module exposes a
**factory**, `make_corpus_route_handler(corpus_ids)`, that closes over the
document-id scope and returns a `RouteHandler`. There is deliberately no
module-level `ROUTE_HANDLERS["corpus"] = ...` registration here (unlike
`web_route_handler`, which needs no per-run parameterization) -- a corpus
handler is meaningless without knowing which documents to search.

Wiring for the orchestrator (TG 04.4, `scripts/run_heavy.py`):

    from ingest.corpus_route import make_corpus_route_handler
    from ingest.routing import ROUTE_HANDLERS, execute_routing

    handlers = dict(ROUTE_HANDLERS)
    if manifest.corpus_ids:
        handlers["corpus"] = make_corpus_route_handler(manifest.corpus_ids)
    records = await execute_routing(records, manifest, handlers=handlers)

Passing `handlers=None` (the default) when `manifest.corpus_ids` is falsy is
also fine: `decide_route` never proposes `"corpus"` as a candidate unless
`"corpus" in manifest.available_routes`, which itself requires a non-empty
`corpus_ids` (see `utils/run_config.py:ResourceManifest.available_routes`).
So an un-registered `"corpus"` handler only matters if a caller manually
constructs a policy/manifest mismatch; `execute_routing` already handles a
missing handler gracefully (records "no handler registered" in
`routing_reason` rather than raising).

Failure handling, mirroring `web_route_handler`/`evaluate_alignment`:
    - No usable claim text on the record -> returns `None` (no verdict).
    - `search_corpus` returns `None` (corpus API unavailable) -> returns
      `None`. The claim stays without a corpus verdict; nothing raises.
    - `search_corpus` succeeds but returns no chunks -> a `RouteVerdict` IS
      recorded (`verdict=CorpusVerdict.NO_CORPUS_HITS`), the same way
      `gather_evidence` in `ingest/alignment.py` records
      `NOTE_NOT_IN_VAULT`/`INSUFFICIENT_VAULT_CONTENT` verdicts without an
      LLM call -- "we looked and found nothing" is itself useful audit
      trail, distinct from "we couldn't look."
    - The evaluation call fails (`call_llm_with_structured_output` returns
      `None`) -> returns `None`, no verdict recorded (mirrors
      `evaluate_alignment`'s "LLM returns None -> skip, no verdict").
No exception is caught-and-swallowed inside the handler beyond what
`search_corpus`/`call_llm_with_structured_output` already guarantee return
`None` rather than raising; any other exception propagates to
`execute_routing`, which is the single place responsible for turning a
handler failure into a recorded `routing_reason` rather than aborting the
run (same contract as `web_route_handler`).
"""

import logging
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from claim_verifier.evidence_summarization import summarize_evidence_for_claim
from claim_verifier.schemas import Evidence
from ingest.corpus_client import CorpusSearchResult, search_corpus
from ingest.routing import RouteHandler
from utils import call_llm_with_structured_output, get_llm
from utils.claim_record import ClaimRecord, CorpusVerdict, RouteVerdict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Evaluation output + prompts
# ---------------------------------------------------------------------------


class CorpusEvaluationOutput(BaseModel):
    """Structured LLM output for a single claim-vs-corpus-evidence check."""

    verdict: Literal["corpus_supported", "corpus_contradicted", "corpus_insufficient"] = Field(
        description="Whether the corpus evidence supports, contradicts, or fails to support the claim"
    )
    reasoning: str = Field(
        description="Why the evidence does or doesn't support the claim"
    )


CORPUS_EVALUATION_SYSTEM_PROMPT = """You are verifying a factual claim against evidence retrieved from the \
author's own research corpus (ingested papers, datasets, and internal documents).

Decide whether the evidence:
- corpus_supported: clearly supports the claim
- corpus_contradicted: clearly contradicts the claim
- corpus_insufficient: does not provide enough information to judge either \
way (too tangential, too sparse, or simply silent on the claim)

Base your judgment strictly on the provided text. Do not use outside
knowledge. Choose exactly one verdict."""

CORPUS_EVALUATION_HUMAN_PROMPT = """Claim:
{claim_text}

Corpus evidence:
{evidence_block}"""


def _format_corpus_evidence(evidence_items: List[Evidence]) -> str:
    if not evidence_items:
        return "No corpus evidence was retrieved."

    return "\n\n".join(
        f"Source {i + 1}: {item.url}\n"
        + (f"Title: {item.title}\n" if item.title else "")
        + f"Text: {item.text.strip()}\n---"
        for i, item in enumerate(evidence_items)
    )


async def _evaluate_corpus_evidence(
    claim_text: str, evidence_items: List[Evidence]
) -> Optional[CorpusEvaluationOutput]:
    """High-tier evaluation of a claim against wrapped/summarized corpus evidence.

    Route-local (not a call into `claim_verifier`'s evaluate_evidence node --
    see the module docstring for why). Never downgrade the tier: this is the
    hard quality gate on the corpus route, the same as `evaluate_evidence`
    is for web and `evaluate_alignment` is for vault-aligned.
    """
    llm = get_llm(tier="high")

    messages = [
        ("system", CORPUS_EVALUATION_SYSTEM_PROMPT),
        (
            "human",
            CORPUS_EVALUATION_HUMAN_PROMPT.format(
                claim_text=claim_text,
                evidence_block=_format_corpus_evidence(evidence_items),
            ),
        ),
    ]

    return await call_llm_with_structured_output(
        llm=llm,
        output_class=CorpusEvaluationOutput,
        messages=messages,
        context_desc=f"corpus evaluation for claim '{claim_text}'",
    )


# ---------------------------------------------------------------------------
# Evidence wrapping + provenance
# ---------------------------------------------------------------------------


def _wrap_evidence(search_result: CorpusSearchResult) -> List[Evidence]:
    """Wrap every retrieved chunk as a `claim_verifier` `Evidence` item.

    `url` is a synthetic `corpus://<document_id>#<chunk_id>` reference (no
    real corpus chunks are addressable over HTTP) -- distinct from
    `RouteVerdict.provenance`, which records the same refs in the audit
    trail. `text` includes the chunk's `context` enrichment (surrounding
    passage) ahead of the chunk's own `text`, when present, so a summarizer
    or evaluator reading just the wrapped `Evidence.text` still has the
    surrounding context the corpus API supplied.
    """
    evidence_items: List[Evidence] = []

    for doc in search_result.results:
        for chunk in doc.chunks:
            text = chunk.text.strip()
            if chunk.context and chunk.context.strip():
                text = f"{chunk.context.strip()}\n\n{text}"

            evidence_items.append(
                Evidence(
                    url=f"corpus://{doc.document_id}#{chunk.chunk_id}",
                    text=text,
                    title=doc.title,
                )
            )

    return evidence_items


def _build_provenance(search_result: CorpusSearchResult) -> Optional[str]:
    """Render `document_id#chunk_id` (plus section, when known) provenance refs."""
    refs = [
        f"{doc.document_id}#{chunk.chunk_id}"
        + (f" ({chunk.section})" if chunk.section else "")
        for doc in search_result.results
        for chunk in doc.chunks
    ]
    return ", ".join(refs) or None


# ---------------------------------------------------------------------------
# Route core + factory
# ---------------------------------------------------------------------------


async def _corpus_route_core(
    record: ClaimRecord, corpus_ids: List[str]
) -> Optional[RouteVerdict]:
    """Verify one claim against the corpus scoped to `corpus_ids`.

    See the module docstring for the full failure-handling contract.
    """
    claim_text = record.claim_text
    if not claim_text or not claim_text.strip():
        logger.warning("corpus_route: no usable claim text on record; skipping")
        return None

    result = await search_corpus(claim_text, document_ids=corpus_ids)
    if result is None:
        logger.warning(
            "corpus_route: corpus search unavailable for claim '%s'", claim_text
        )
        return None

    evidence_items = _wrap_evidence(result)
    if not evidence_items:
        route_verdict = RouteVerdict(
            route="corpus",
            verdict=CorpusVerdict.NO_CORPUS_HITS.value,
            reasoning="No corpus chunks matched this claim.",
            provenance=None,
            provenance_type="corpus_doc_id",
        )
        record.route_verdicts.append(route_verdict)
        return route_verdict

    evidence_for_evaluation = await summarize_evidence_for_claim(
        claim_text, evidence_items
    )

    evaluation = await _evaluate_corpus_evidence(claim_text, evidence_for_evaluation)
    if evaluation is None:
        logger.warning(
            "corpus_route: evaluation failed for claim '%s'; no verdict recorded",
            claim_text,
        )
        return None

    route_verdict = RouteVerdict(
        route="corpus",
        verdict=evaluation.verdict,
        reasoning=evaluation.reasoning,
        provenance=_build_provenance(result),
        provenance_type="corpus_doc_id",
    )
    record.route_verdicts.append(route_verdict)
    return route_verdict


def make_corpus_route_handler(corpus_ids: List[str]) -> RouteHandler:
    """Build a `RouteHandler` scoped to `corpus_ids`.

    See the module docstring's "Manifest scoping" section for why this is a
    factory rather than a module-level `ROUTE_HANDLERS["corpus"]` entry, and
    for the exact wiring the orchestrator (TG 04.4) should use.
    """

    async def _handler(record: ClaimRecord) -> Optional[RouteVerdict]:
        return await _corpus_route_core(record, corpus_ids)

    return _handler
