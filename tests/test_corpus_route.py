"""Tests for the corpus verification route (TG 04.3).

``ingest/corpus_route.py`` registers `"corpus"` as a real verification
route: corpus search -> evidence wrap -> mid-tier summarization -> high-tier
LLM evaluation -> `RouteVerdict(route="corpus")` with document-id
provenance. Reuses `claim_verifier.evidence_summarization.summarize_evidence_for_claim`
unmodified; evaluation is route-local (not `claim_verifier`'s
evaluate_evidence node -- see the module docstring for why).

See ingest/corpus_route.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claim_verifier.schemas import Evidence, Verdict, VerificationResult
from ingest.corpus_client import ChunkScores, CorpusChunk, CorpusDocumentResult, CorpusSearchResult
from ingest.corpus_route import (
    CorpusEvaluationOutput,
    make_corpus_route_handler,
)
from ingest.routing import (
    POLICY,
    ROUTE_HANDLERS,
    decide_route,
    execute_routing,
    route_decision,
)
from utils.claim_record import CitationStatus, ClaimRecord, CorpusVerdict, DraftPosition, RouteVerdict
from utils.run_config import ResourceManifest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def make_verdict(claim_text="A claim.", original_index=0):
    return Verdict(
        claim_text=claim_text,
        disambiguated_sentence=claim_text,
        original_sentence=claim_text,
        original_index=original_index,
        result=VerificationResult.SUPPORTED,
        reasoning="Test verdict.",
        sources=[],
    )


def make_record(claim_text="A claim.", triage_class=None, route_verdicts=None):
    return ClaimRecord(
        web_verdict=make_verdict(claim_text),
        citation_status=CitationStatus.CITATION_FREE,
        cite_set=[],
        position=DraftPosition(sentence_index=0),
        route_verdicts=route_verdicts or [],
        triage_class=triage_class,
    )


def make_search_result(document_id="doc-1", chunk_id="chunk-1", context="Some context."):
    return CorpusSearchResult(
        query="q",
        search_mode="hybrid",
        total_chunks=1,
        total_documents=1,
        results=[
            CorpusDocumentResult(
                document_id=document_id,
                title="A Test Paper",
                authors=[{"first_name": "Ana", "last_name": "Kim"}],
                publication_year=2023,
                doi="10.1/xyz",
                chunks=[
                    CorpusChunk(
                        chunk_id=chunk_id,
                        text="The measured value was 42.",
                        section="Results",
                        context=context,
                        token_count=10,
                        scores=ChunkScores(dense=0.9, fts_rank=None, rrf=0.5, rerank=None),
                    )
                ],
            )
        ],
    )


def empty_search_result():
    return CorpusSearchResult(
        query="q", search_mode="hybrid", total_chunks=0, total_documents=0, results=[]
    )


# ---------------------------------------------------------------------------
# _corpus_route_core (via make_corpus_route_handler) -- shape + provenance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corpus_route_supported_verdict_shape_and_provenance():
    record = make_record(claim_text="The measured value was 42.")
    search_result = make_search_result()

    evaluation = CorpusEvaluationOutput(
        verdict="corpus_supported", reasoning="Directly confirmed by the paper."
    )

    with patch(
        "ingest.corpus_route.search_corpus", new=AsyncMock(return_value=search_result)
    ), patch(
        "ingest.corpus_route.summarize_evidence_for_claim",
        new=AsyncMock(side_effect=lambda claim_text, items: items),
    ), patch(
        "ingest.corpus_route._evaluate_corpus_evidence",
        new=AsyncMock(return_value=evaluation),
    ):
        handler = make_corpus_route_handler(["doc-1"])
        result = await handler(record)

    assert isinstance(result, RouteVerdict)
    assert result.route == "corpus"
    assert result.verdict == "corpus_supported"
    assert result.reasoning == "Directly confirmed by the paper."
    assert result.provenance_type == "corpus_doc_id"
    assert "doc-1" in result.provenance
    assert "chunk-1" in result.provenance
    assert record.route_verdicts == [result]


@pytest.mark.asyncio
async def test_corpus_route_contradicted_verdict():
    record = make_record(claim_text="The measured value was 42.")
    search_result = make_search_result()

    evaluation = CorpusEvaluationOutput(
        verdict="corpus_contradicted", reasoning="The paper reports a different value."
    )

    with patch(
        "ingest.corpus_route.search_corpus", new=AsyncMock(return_value=search_result)
    ), patch(
        "ingest.corpus_route.summarize_evidence_for_claim",
        new=AsyncMock(side_effect=lambda claim_text, items: items),
    ), patch(
        "ingest.corpus_route._evaluate_corpus_evidence",
        new=AsyncMock(return_value=evaluation),
    ):
        handler = make_corpus_route_handler(["doc-1"])
        result = await handler(record)

    assert result.verdict == "corpus_contradicted"
    assert record.route_verdicts == [result]


# ---------------------------------------------------------------------------
# No hits / corpus unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_corpus_hits_records_no_corpus_hits_verdict():
    record = make_record(claim_text="An obscure claim.")

    with patch(
        "ingest.corpus_route.search_corpus",
        new=AsyncMock(return_value=empty_search_result()),
    ), patch(
        "ingest.corpus_route._evaluate_corpus_evidence", new_callable=AsyncMock
    ) as mock_eval:
        handler = make_corpus_route_handler(["doc-1"])
        result = await handler(record)

    mock_eval.assert_not_called()
    assert isinstance(result, RouteVerdict)
    assert result.route == "corpus"
    assert result.verdict == CorpusVerdict.NO_CORPUS_HITS.value
    assert record.route_verdicts == [result]


@pytest.mark.asyncio
async def test_corpus_client_returns_none_handler_returns_none():
    """API-down soft failure: handler returns None, no verdict recorded, run continues."""
    record = make_record(claim_text="A claim.")

    with patch(
        "ingest.corpus_route.search_corpus", new=AsyncMock(return_value=None)
    ), patch(
        "ingest.corpus_route._evaluate_corpus_evidence", new_callable=AsyncMock
    ) as mock_eval:
        handler = make_corpus_route_handler(["doc-1"])
        result = await handler(record)

    mock_eval.assert_not_called()
    assert result is None
    assert record.route_verdicts == []


@pytest.mark.asyncio
async def test_no_usable_claim_text_returns_none():
    record = ClaimRecord(
        web_verdict=None,
        citation_status=CitationStatus.CITATION_FREE,
        cite_set=[],
        position=DraftPosition(sentence_index=0),
    )

    with patch(
        "ingest.corpus_route.search_corpus", new_callable=AsyncMock
    ) as mock_search:
        handler = make_corpus_route_handler(["doc-1"])
        result = await handler(record)

    mock_search.assert_not_called()
    assert result is None
    assert record.route_verdicts == []


@pytest.mark.asyncio
async def test_evaluation_returns_none_no_verdict_recorded():
    record = make_record(claim_text="A claim.")
    search_result = make_search_result()

    with patch(
        "ingest.corpus_route.search_corpus", new=AsyncMock(return_value=search_result)
    ), patch(
        "ingest.corpus_route.summarize_evidence_for_claim",
        new=AsyncMock(side_effect=lambda claim_text, items: items),
    ), patch(
        "ingest.corpus_route._evaluate_corpus_evidence",
        new=AsyncMock(return_value=None),
    ):
        handler = make_corpus_route_handler(["doc-1"])
        result = await handler(record)

    assert result is None
    assert record.route_verdicts == []


# ---------------------------------------------------------------------------
# Evaluation tier + summarization invocation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluation_called_at_high_tier():
    record = make_record(claim_text="A claim.")
    search_result = make_search_result()

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=CorpusEvaluationOutput(
            verdict="corpus_insufficient", reasoning="Not enough to tell."
        )
    )

    with patch(
        "ingest.corpus_route.search_corpus", new=AsyncMock(return_value=search_result)
    ), patch(
        "ingest.corpus_route.summarize_evidence_for_claim",
        new=AsyncMock(side_effect=lambda claim_text, items: items),
    ), patch(
        "ingest.corpus_route.get_llm", return_value=mock_llm
    ) as mock_get_llm:
        handler = make_corpus_route_handler(["doc-1"])
        result = await handler(record)

    mock_get_llm.assert_called_once_with(tier="high")
    assert result.verdict == "corpus_insufficient"


@pytest.mark.asyncio
async def test_summarization_invoked_exactly_once():
    record = make_record(claim_text="A claim.")
    search_result = make_search_result()

    evaluation = CorpusEvaluationOutput(verdict="corpus_supported", reasoning="Yes.")

    with patch(
        "ingest.corpus_route.search_corpus", new=AsyncMock(return_value=search_result)
    ), patch(
        "ingest.corpus_route.summarize_evidence_for_claim",
        new=AsyncMock(side_effect=lambda claim_text, items: items),
    ) as mock_summarize, patch(
        "ingest.corpus_route._evaluate_corpus_evidence",
        new=AsyncMock(return_value=evaluation),
    ):
        handler = make_corpus_route_handler(["doc-1"])
        await handler(record)

    mock_summarize.assert_awaited_once()
    args, _ = mock_summarize.call_args
    assert args[0] == "A claim."
    assert len(args[1]) == 1
    assert isinstance(args[1][0], Evidence)
    assert args[1][0].url == "corpus://doc-1#chunk-1"


@pytest.mark.asyncio
async def test_summarization_respects_config_switch_disabled():
    """When summarize_evidence is off, summarize_evidence_for_claim (the real,
    unmocked function) returns evidence unchanged -- corpus_route must still
    only call it once and feed its result straight to evaluation."""
    record = make_record(claim_text="A claim.")
    search_result = make_search_result()

    evaluation = CorpusEvaluationOutput(verdict="corpus_supported", reasoning="Yes.")

    with patch(
        "ingest.corpus_route.search_corpus", new=AsyncMock(return_value=search_result)
    ), patch(
        "claim_verifier.evidence_summarization.EVIDENCE_SUMMARIZATION_CONFIG",
        {"enabled": False, "tier": "mid"},
    ), patch(
        "ingest.corpus_route._evaluate_corpus_evidence",
        new=AsyncMock(return_value=evaluation),
    ) as mock_eval:
        handler = make_corpus_route_handler(["doc-1"])
        result = await handler(record)

    # Config-off short-circuit in summarize_evidence_for_claim means the
    # evaluator receives the raw wrapped evidence, unsummarized.
    eval_args, _ = mock_eval.call_args
    assert eval_args[0] == "A claim."
    assert eval_args[1][0].text.startswith("Some context.")
    assert result.verdict == "corpus_supported"


# ---------------------------------------------------------------------------
# decide_route / execute_routing integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_never_web_claim_with_corpus_ids_routes_to_corpus():
    record = make_record(triage_class="novel-result")
    manifest = ResourceManifest(draft_path="draft.md", corpus_ids=["doc-1"])

    result = decide_route(record, manifest.available_routes)

    assert result.decision == route_decision("corpus")


@pytest.mark.asyncio
async def test_manifest_without_corpus_ids_corpus_route_not_offered():
    record = make_record(triage_class="dataset-dependent")
    manifest = ResourceManifest(draft_path="draft.md")

    assert "corpus" not in manifest.available_routes
    result = decide_route(record, manifest.available_routes)

    from ingest.routing import UNVERIFIABLE

    assert result.decision == UNVERIFIABLE


@pytest.mark.asyncio
async def test_execute_routing_dispatches_never_web_claim_to_corpus_handler():
    record = make_record(claim_text="A novel finding.", triage_class="novel-result")
    manifest = ResourceManifest(draft_path="draft.md", corpus_ids=["doc-1"])
    search_result = make_search_result()

    evaluation = CorpusEvaluationOutput(verdict="corpus_supported", reasoning="Matches.")

    handlers = dict(ROUTE_HANDLERS)
    handlers["corpus"] = make_corpus_route_handler(manifest.corpus_ids)

    with patch(
        "ingest.corpus_route.search_corpus", new=AsyncMock(return_value=search_result)
    ), patch(
        "ingest.corpus_route.summarize_evidence_for_claim",
        new=AsyncMock(side_effect=lambda claim_text, items: items),
    ), patch(
        "ingest.corpus_route._evaluate_corpus_evidence",
        new=AsyncMock(return_value=evaluation),
    ):
        result_records = await execute_routing([record], manifest, handlers=handlers)

    assert result_records[0].routing_decision == route_decision("corpus")
    corpus_verdicts = [rv for rv in record.route_verdicts if rv.route == "corpus"]
    assert len(corpus_verdicts) == 1
    assert corpus_verdicts[0].verdict == "corpus_supported"


@pytest.mark.asyncio
async def test_execute_routing_without_corpus_handler_records_no_handler_reason():
    """Manifest declares corpus_ids (so decide_route picks 'corpus'), but the
    caller didn't register a handler -- execute_routing must not raise."""
    record = make_record(claim_text="A novel finding.", triage_class="novel-result")
    manifest = ResourceManifest(draft_path="draft.md", corpus_ids=["doc-1"])

    result_records = await execute_routing([record], manifest, handlers={})

    assert result_records[0].routing_decision == route_decision("corpus")
    assert "no handler registered" in result_records[0].routing_reason


@pytest.mark.asyncio
async def test_corpus_handler_failure_is_recorded_and_run_continues():
    record = make_record(claim_text="A novel finding.", triage_class="novel-result")
    manifest = ResourceManifest(draft_path="draft.md", corpus_ids=["doc-1"])

    async def failing_handler(rec):
        raise ValueError("corpus API exploded")

    result_records = await execute_routing(
        [record], manifest, handlers={"corpus": failing_handler}
    )

    assert "handler error" in result_records[0].routing_reason
    assert "corpus API exploded" in result_records[0].routing_reason


def test_policy_never_web_row_declares_corpus_candidate():
    """POLICY's never-web row should declare 'corpus' as a candidate route
    (the anticipated Phase 04 change) without altering the web-eligible rows."""
    never_web_row = next(row for row in POLICY if row.name == "never-web")
    assert "corpus" in never_web_row.candidate_routes

    general_row = next(row for row in POLICY if row.name == "general")
    assert general_row.candidate_routes == ("web",)
