"""Async HTTP client for the doc-rag-backend corpus search API (TG 04.2.1).

Talks to the deployed doc-rag-backend service (default
``https://api.ragtogo.com``, see ``config.toml``'s ``[corpus_api]``
section) for two things:
    - `search_corpus` -- hybrid/dense/fts search over ingested documents,
      returning matching chunks grouped by document.
    - `list_documents` -- paginated listing of ingested documents, used for
      DB-content visibility and citation-to-document-id mapping.

The backend has no metadata search endpoint (a recorded gap), so
`map_citations_to_document_ids` matches author-year citation strings
(e.g. "Kim 2023", "(Zeng et al. 2026)") against `list_documents` output
client-side: surname substring + publication_year equality, no LLM calls.
Ambiguous citations (matching more than one document) are dropped rather
than guessed.

Every public function degrades gracefully -- connection errors, non-2xx
responses, and unparseable response bodies are logged as warnings and
return `None` (`search_corpus`) or `[]` / partial results (`list_documents`)
rather than raising. The route handler upstream (TG 04.3) treats an
unavailable corpus as a soft failure, not a pipeline abort.

Auth: `X-API-Key` header on `/search` and `/documents`, sent only when
`utils.settings.settings.rag_api_key` is set (dev-mode backends run with
no key configured, see `app/api/auth.py` in doc-rag-backend).
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

import httpx
from pydantic import BaseModel

from utils.config import config as _config
from utils.settings import settings

logger = logging.getLogger(__name__)

_CORPUS_CONFIG = _config.get("corpus_api", {})

DEFAULT_BASE_URL: str = _CORPUS_CONFIG.get("base_url", "https://api.ragtogo.com")
DEFAULT_MODE: str = _CORPUS_CONFIG.get("mode", "hybrid")
DEFAULT_TOP_K: int = _CORPUS_CONFIG.get("top_k", 10)

DEFAULT_LIST_LIMIT = 100
REQUEST_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ChunkScores(BaseModel):
    """Relevance scores from different retrieval methods."""

    dense: Optional[float] = None
    fts_rank: Optional[int] = None
    rrf: Optional[float] = None
    rerank: Optional[float] = None


class CorpusChunk(BaseModel):
    """A single retrieved chunk with scores and context."""

    chunk_id: str
    text: str
    section: Optional[str] = None
    context: Optional[str] = None
    token_count: int
    scores: ChunkScores


class CorpusDocumentResult(BaseModel):
    """All matched chunks from one document, plus its citation metadata."""

    document_id: str
    title: Optional[str] = None
    authors: Optional[List[dict]] = None
    publication_year: Optional[int] = None
    doi: Optional[str] = None
    chunks: List[CorpusChunk]


class CorpusSearchResult(BaseModel):
    """Parsed `/search` response."""

    query: str
    search_mode: str
    total_chunks: int
    total_documents: int
    results: List[CorpusDocumentResult]


class CorpusDocument(BaseModel):
    """A single entry from `/documents` (metadata only, no content)."""

    id: str
    title: Optional[str] = None
    authors: Optional[List[dict]] = None
    doi: Optional[str] = None
    openalex_id: Optional[str] = None
    zotero_key: Optional[str] = None
    zotero_library_id: Optional[str] = None
    publication_year: Optional[int] = None
    venue: Optional[str] = None


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------


def _build_client() -> httpx.AsyncClient:
    """Construct the HTTP client. A separate function so tests can swap in
    an `httpx.MockTransport` without touching real network settings."""
    return httpx.AsyncClient(base_url=DEFAULT_BASE_URL, timeout=REQUEST_TIMEOUT)


def _auth_headers() -> Dict[str, str]:
    if settings.rag_api_key:
        return {"X-API-Key": settings.rag_api_key}
    return {}


# ---------------------------------------------------------------------------
# search_corpus
# ---------------------------------------------------------------------------


async def search_corpus(
    query: str,
    document_ids: Optional[List[str]] = None,
    *,
    top_k: Optional[int] = None,
    mode: Optional[str] = None,
) -> Optional[CorpusSearchResult]:
    """Search the corpus for chunks relevant to `query`.

    `top_k` and `mode` default to `config.toml`'s `[corpus_api]` section
    (`DEFAULT_TOP_K`, `DEFAULT_MODE`). `document_ids`, when given, is
    joined into the comma-separated form the backend's `/search` endpoint
    expects.

    Returns `None` on any failure -- connection error, non-200 response, or
    a response body that doesn't match the expected shape -- and never
    raises. Callers treat `None` as "corpus unavailable for this query".
    """
    params: Dict[str, str] = {
        "q": query,
        "mode": mode or DEFAULT_MODE,
        "top_k": str(top_k or DEFAULT_TOP_K),
    }
    if document_ids:
        params["document_ids"] = ",".join(document_ids)

    try:
        async with _build_client() as client:
            response = await client.get(
                "/search", params=params, headers=_auth_headers()
            )
    except httpx.HTTPError as exc:
        logger.warning("Corpus search request failed for query %r: %s", query, exc)
        return None

    if response.status_code != 200:
        logger.warning(
            "Corpus search returned status %d for query %r",
            response.status_code,
            query,
        )
        return None

    try:
        return CorpusSearchResult.model_validate(response.json())
    except Exception as exc:
        logger.warning(
            "Corpus search response failed to parse for query %r: %s", query, exc
        )
        return None


# ---------------------------------------------------------------------------
# list_documents
# ---------------------------------------------------------------------------


async def list_documents(
    offset: int = 0, limit: int = DEFAULT_LIST_LIMIT
) -> List[CorpusDocument]:
    """List all ingested documents via paginated `GET /documents`.

    Loops, advancing `offset` by `limit` each call, until a page returns
    fewer than `limit` documents. On failure mid-loop (connection error,
    non-200, unparseable body), returns whatever pages were already
    collected rather than discarding them -- never raises.
    """
    documents: List[CorpusDocument] = []
    current_offset = offset

    while True:
        try:
            async with _build_client() as client:
                response = await client.get(
                    "/documents",
                    params={"offset": current_offset, "limit": limit},
                    headers=_auth_headers(),
                )
        except httpx.HTTPError as exc:
            logger.warning("Corpus list_documents request failed: %s", exc)
            return documents

        if response.status_code != 200:
            logger.warning(
                "Corpus list_documents returned status %d", response.status_code
            )
            return documents

        try:
            page = [CorpusDocument.model_validate(item) for item in response.json()]
        except Exception as exc:
            logger.warning("Corpus list_documents response failed to parse: %s", exc)
            return documents

        documents.extend(page)
        if len(page) < limit:
            return documents

        current_offset += limit


# ---------------------------------------------------------------------------
# map_citations_to_document_ids
# ---------------------------------------------------------------------------

_CITATION_YEAR_RE = re.compile(r"\d{4}")
_CITATION_SURNAME_RE = re.compile(r"[A-Z][a-zA-Z\-]+")

# Leading tokens that show up before a surname in author-year citations
# (parenthesis, "et al.") and carry no identifying signal on their own.
_CITATION_SURNAME_STOPWORDS = {"Et", "Al"}


def _extract_citation_parts(citation: str) -> Optional[tuple]:
    """Pull a surname and a 4-digit year out of a citation string.

    Handles both bare (`"Kim 2023"`) and parenthetical/et-al forms
    (`"(Kim et al. 2023)"`). Returns `None` when either part can't be
    found, so the caller skips the citation rather than guessing.
    """
    year_match = _CITATION_YEAR_RE.search(citation)
    if year_match is None:
        return None

    surname = None
    for match in _CITATION_SURNAME_RE.finditer(citation):
        word = match.group(0)
        if word in _CITATION_SURNAME_STOPWORDS:
            continue
        surname = word
        break

    if surname is None:
        return None

    return surname, int(year_match.group(0))


def map_citations_to_document_ids(
    citations: List[str], documents: List[CorpusDocument]
) -> Dict[str, str]:
    """Match author-year citation strings to document IDs client-side.

    The backend has no metadata search endpoint, so this is a conservative
    surname-substring + year-equality match: a citation matches a document
    when the citation's year equals the document's `publication_year` AND
    the citation's surname appears (case-insensitive) in one of the
    document's `authors` entries' `last_name`. Citations that don't parse
    (no year or no capitalized surname-like token) are skipped; citations
    matching more than one document are dropped rather than guessed, since
    a wrong mapping is worse than no mapping.
    """
    result: Dict[str, str] = {}

    for citation in citations:
        parts = _extract_citation_parts(citation)
        if parts is None:
            continue
        surname, year = parts
        surname_lower = surname.lower()

        matches = [
            doc
            for doc in documents
            if doc.publication_year == year
            and doc.authors
            and any(
                surname_lower in (author.get("last_name") or "").lower()
                for author in doc.authors
            )
        ]

        if len(matches) == 1:
            result[citation] = matches[0].id

    return result
