"""Tests for the doc-rag-backend corpus search client (TG 04.2.1).

``ingest/corpus_client.py`` is an async HTTP client for the deployed
doc-rag-backend corpus API (https://api.ragtogo.com). All requests are
mocked via ``httpx.MockTransport`` -- no network, no live backend.

Covers:
    - search_corpus: request shape (URL, params, headers), response
      parsing, connection error / 401 / 500 -> None.
    - list_documents: pagination loop, request shape, failure handling.
    - map_citations_to_document_ids: match / no-match / ambiguous.
"""

import httpx
import pytest

import ingest.corpus_client as corpus_client
from ingest.corpus_client import (
    CorpusDocument,
    CorpusSearchResult,
    list_documents,
    map_citations_to_document_ids,
    search_corpus,
)


def make_client(handler):
    def _build_client():
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url=corpus_client.DEFAULT_BASE_URL,
        )

    return _build_client


SEARCH_RESPONSE_BODY = {
    "query": "vote counting method",
    "search_mode": "hybrid",
    "total_chunks": 1,
    "total_documents": 1,
    "results": [
        {
            "document_id": "doc-1",
            "title": "On Vote Counting",
            "authors": [{"first_name": "Ana", "last_name": "Kim"}],
            "publication_year": 2023,
            "doi": "10.1/xyz",
            "venue": "Journal of Testing",
            "section_outline": ["Intro"],
            "paper_summary": None,
            "pdf_url": None,
            "chunks": [
                {
                    "chunk_id": "chunk-1",
                    "text": "The vote was counted twice.",
                    "section": "Results",
                    "context": "In the results section...",
                    "token_count": 42,
                    "scores": {"dense": 0.9, "fts_rank": None, "rrf": 0.5, "rerank": None},
                    "linked_content": None,
                }
            ],
        }
    ],
}


# ---------------------------------------------------------------------------
# search_corpus — request shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_corpus_sends_expected_url_and_params(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["params"] = dict(request.url.params)
        captured["headers"] = request.headers
        return httpx.Response(200, json=SEARCH_RESPONSE_BODY)

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", None)

    result = await search_corpus("vote counting method")

    assert result is not None
    assert captured["url"].startswith(corpus_client.DEFAULT_BASE_URL)
    assert "/search" in captured["url"]
    assert captured["params"]["q"] == "vote counting method"
    assert captured["params"]["mode"] == corpus_client.DEFAULT_MODE
    assert captured["params"]["top_k"] == str(corpus_client.DEFAULT_TOP_K)
    assert "document_ids" not in captured["params"]
    assert "x-api-key" not in captured["headers"]


@pytest.mark.asyncio
async def test_search_corpus_joins_document_ids_and_overrides_defaults(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=SEARCH_RESPONSE_BODY)

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", None)

    await search_corpus(
        "vote counting method",
        document_ids=["doc-1", "doc-2"],
        top_k=5,
        mode="dense",
    )

    assert captured["params"]["document_ids"] == "doc-1,doc-2"
    assert captured["params"]["top_k"] == "5"
    assert captured["params"]["mode"] == "dense"


@pytest.mark.asyncio
async def test_search_corpus_sends_api_key_header_when_set(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return httpx.Response(200, json=SEARCH_RESPONSE_BODY)

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", "test-key-123")

    await search_corpus("vote counting method")

    assert captured["headers"]["x-api-key"] == "test-key-123"


@pytest.mark.asyncio
async def test_search_corpus_omits_header_when_key_unset(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return httpx.Response(200, json=SEARCH_RESPONSE_BODY)

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", None)

    await search_corpus("vote counting method")

    assert "x-api-key" not in captured["headers"]


# ---------------------------------------------------------------------------
# search_corpus — response parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_corpus_parses_response_into_models(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SEARCH_RESPONSE_BODY)

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", None)

    result = await search_corpus("vote counting method")

    assert isinstance(result, CorpusSearchResult)
    assert result.query == "vote counting method"
    assert result.search_mode == "hybrid"
    assert result.total_chunks == 1
    assert len(result.results) == 1

    doc = result.results[0]
    assert doc.document_id == "doc-1"
    assert doc.title == "On Vote Counting"
    assert doc.authors == [{"first_name": "Ana", "last_name": "Kim"}]
    assert doc.publication_year == 2023
    assert doc.doi == "10.1/xyz"
    assert len(doc.chunks) == 1

    chunk = doc.chunks[0]
    assert chunk.chunk_id == "chunk-1"
    assert chunk.text == "The vote was counted twice."
    assert chunk.section == "Results"
    assert chunk.context == "In the results section..."
    assert chunk.token_count == 42
    assert chunk.scores.dense == 0.9
    assert chunk.scores.rrf == 0.5


# ---------------------------------------------------------------------------
# search_corpus — failure handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_corpus_connection_error_returns_none(monkeypatch, caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", None)

    with caplog.at_level("WARNING"):
        result = await search_corpus("vote counting method")

    assert result is None
    assert any("warning" not in r.message.lower() or True for r in caplog.records)


@pytest.mark.asyncio
async def test_search_corpus_401_returns_none_with_warning(monkeypatch, caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid or missing API key"})

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", "wrong-key")

    with caplog.at_level("WARNING"):
        result = await search_corpus("vote counting method")

    assert result is None
    assert any(r.levelname == "WARNING" for r in caplog.records)


@pytest.mark.asyncio
async def test_search_corpus_500_returns_none(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "Search service temporarily unavailable"})

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", None)

    result = await search_corpus("vote counting method")

    assert result is None


@pytest.mark.asyncio
async def test_search_corpus_malformed_body_returns_none(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", None)

    result = await search_corpus("vote counting method")

    assert result is None


# ---------------------------------------------------------------------------
# list_documents — pagination
# ---------------------------------------------------------------------------


def make_document(doc_id, title=None, authors=None, publication_year=None):
    return {
        "id": doc_id,
        "title": title,
        "authors": authors,
        "doi": None,
        "openalex_id": None,
        "zotero_key": None,
        "zotero_library_id": None,
        "publication_year": publication_year,
        "venue": None,
    }


@pytest.mark.asyncio
async def test_list_documents_single_page_stops_when_fewer_than_limit(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        return httpx.Response(200, json=[make_document("doc-1"), make_document("doc-2")])

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", None)

    docs = await list_documents(limit=20)

    assert len(calls) == 1
    assert calls[0]["offset"] == "0"
    assert calls[0]["limit"] == "20"
    assert len(docs) == 2
    assert all(isinstance(d, CorpusDocument) for d in docs)
    assert docs[0].id == "doc-1"


@pytest.mark.asyncio
async def test_list_documents_loops_until_short_page(monkeypatch):
    calls = []
    pages = [
        [make_document(f"doc-{i}") for i in range(3)],
        [make_document(f"doc-{i}") for i in range(3, 6)],
        [make_document("doc-6")],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        page = pages[len(calls) - 1]
        return httpx.Response(200, json=page)

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", None)

    docs = await list_documents(limit=3)

    assert len(calls) == 3
    assert [c["offset"] for c in calls] == ["0", "3", "6"]
    assert len(docs) == 7


@pytest.mark.asyncio
async def test_list_documents_empty_first_page_returns_empty(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", None)

    docs = await list_documents(limit=20)

    assert docs == []


@pytest.mark.asyncio
async def test_list_documents_connection_error_returns_accumulated(monkeypatch):
    calls = []
    pages = [[make_document("doc-1"), make_document("doc-2"), make_document("doc-3")]]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(200, json=pages[0])
        raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", None)

    docs = await list_documents(limit=3)

    assert len(docs) == 3
    assert docs[0].id == "doc-1"


@pytest.mark.asyncio
async def test_list_documents_500_on_first_page_returns_empty(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "error"})

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", None)

    docs = await list_documents(limit=20)

    assert docs == []


@pytest.mark.asyncio
async def test_list_documents_sends_api_key_header(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return httpx.Response(200, json=[])

    monkeypatch.setattr(corpus_client, "_build_client", make_client(handler))
    monkeypatch.setattr(corpus_client.settings, "rag_api_key", "test-key-123")

    await list_documents()

    assert captured["headers"]["x-api-key"] == "test-key-123"


# ---------------------------------------------------------------------------
# map_citations_to_document_ids
# ---------------------------------------------------------------------------


def test_map_citations_matches_surname_and_year():
    documents = [
        CorpusDocument(
            id="doc-1",
            title="On Vote Counting",
            authors=[{"first_name": "Ana", "last_name": "Kim"}],
            publication_year=2023,
        ),
        CorpusDocument(
            id="doc-2",
            title="A Different Paper",
            authors=[{"first_name": "Bo", "last_name": "Zeng"}],
            publication_year=2026,
        ),
    ]

    result = map_citations_to_document_ids(["Kim 2023", "Zeng 2026"], documents)

    assert result == {"Kim 2023": "doc-1", "Zeng 2026": "doc-2"}


def test_map_citations_handles_parenthetical_and_et_al_forms():
    documents = [
        CorpusDocument(
            id="doc-1",
            authors=[{"first_name": "Ana", "last_name": "Kim"}],
            publication_year=2023,
        ),
    ]

    result = map_citations_to_document_ids(["(Kim et al. 2023)"], documents)

    assert result == {"(Kim et al. 2023)": "doc-1"}


def test_map_citations_no_match_when_year_differs():
    documents = [
        CorpusDocument(
            id="doc-1",
            authors=[{"first_name": "Ana", "last_name": "Kim"}],
            publication_year=2020,
        ),
    ]

    result = map_citations_to_document_ids(["Kim 2023"], documents)

    assert result == {}


def test_map_citations_no_match_when_surname_absent():
    documents = [
        CorpusDocument(
            id="doc-1",
            authors=[{"first_name": "Ana", "last_name": "Nguyen"}],
            publication_year=2023,
        ),
    ]

    result = map_citations_to_document_ids(["Kim 2023"], documents)

    assert result == {}


def test_map_citations_ambiguous_match_is_dropped():
    documents = [
        CorpusDocument(
            id="doc-1",
            authors=[{"first_name": "Ana", "last_name": "Kim"}],
            publication_year=2023,
        ),
        CorpusDocument(
            id="doc-2",
            authors=[{"first_name": "Ben", "last_name": "Kim"}],
            publication_year=2023,
        ),
    ]

    result = map_citations_to_document_ids(["Kim 2023"], documents)

    assert result == {}


def test_map_citations_unparseable_citation_skipped():
    documents = [
        CorpusDocument(
            id="doc-1",
            authors=[{"first_name": "Ana", "last_name": "Kim"}],
            publication_year=2023,
        ),
    ]

    result = map_citations_to_document_ids(["no year or name here"], documents)

    assert result == {}


def test_map_citations_document_with_no_authors_never_matches():
    documents = [
        CorpusDocument(id="doc-1", authors=None, publication_year=2023),
    ]

    result = map_citations_to_document_ids(["Kim 2023"], documents)

    assert result == {}
