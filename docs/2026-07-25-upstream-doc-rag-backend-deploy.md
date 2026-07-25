# Upstream Notification — doc-rag-backend Phase 19 Deployed

**Date:** 2026-07-25
**From:** doc-rag-backend (Session CC deploy)
**Affects:** ClaimeAI Phase 04 (corpus RAG route)

## What shipped

Phase 19 ("parse-as-a-service") and several Session CA/CB features are now live at `https://api.ragtogo.com`:

### 1. Per-client API keys

`DOC_RAG_API_KEY` now accepts a comma-separated list. ClaimeAI's existing `RAG_API_KEY` (provisioned Session 9) continues to work — no action needed. If a key rotation is ever required, the backend can issue a new key without invalidating the server's own operational key.

### 2. `POST /parse` endpoint (new)

Standalone PDF parsing without ingestion. Upload a PDF, get structured JSON or Markdown back.

```bash
# JSON (default)
curl -X POST https://api.ragtogo.com/parse \
  -H "X-API-Key: $RAG_API_KEY" \
  -F "file=@paper.pdf"

# Markdown
curl -X POST "https://api.ragtogo.com/parse?format=markdown" \
  -H "X-API-Key: $RAG_API_KEY" \
  -F "file=@paper.pdf"
```

Query params: `format` (json|markdown), `vlm` (true|false — formula/picture VLM, default true), `timeout` (seconds, default 120).

Not needed for the current corpus RAG route, but available if ClaimeAI ever needs to parse PDFs directly (e.g., for inline citation extraction or document preview).

### 3. Metadata filters on `GET /documents` (new)

The gap identified in `2026-07-24-claimeai-first-client-needs.md` §1 is now resolved. Filter params:

| Param | Match type | Example |
|-------|-----------|---------|
| `doi` | Exact | `?doi=10.1234/example` |
| `zotero_key` | Exact | `?zotero_key=QUA78EK3` |
| `year` | Exact (publication_year) | `?year=2023` |
| `title` | Case-insensitive substring | `?title=voting` |
| `author` | Substring against JSONB authors | `?author=Kim` |

Filters combine with AND. No filters = all documents (backward-compatible).

```bash
# Resolve "Kim 2023" to document_id
curl -s -H "X-API-Key: $RAG_API_KEY" \
  "https://api.ragtogo.com/documents?author=Kim&year=2023"
```

This means `map_citations_to_document_ids()` in `ingest/corpus_client.py` can now resolve citations server-side instead of paging through all documents.

### 4. Null-byte sanitization fix

The ingestion failure on Zeng 2026 (BMP PUA characters causing `CharacterNotInRepertoireError`) is fixed. PDFs with font-specific glyphs (ORCID markers, etc.) now parse cleanly.

### 5. Failed Zeng shell cleaned up

`d_-DhOtDP0oL7y` (the empty document row from the failed pre-fix ingestion attempt) has been deleted from the production database. The valid Zeng 2026 document is `d_ZikkNbPZFWWV`.

## Action items for ClaimeAI

1. **Re-ingest the 4 papers** — the OpenAI API key quota issue (Session 9) is a backend concern, not ClaimeAI's. Check with the backend owner whether the key has been topped up. The document rows (`d_OOfQK0u0hSFA`, `d_2IBOCexW_qQY`, `d_wERrWO7aNPBt`, `d_MWigEjhYX4xO`) may need deletion and re-POST if the backend doesn't support re-running failed stages.

2. **Optional improvement:** update `corpus_client.py` to use the new metadata filters on `GET /documents` for citation resolution, replacing any client-side matching logic.

3. **No key changes needed** — existing `RAG_API_KEY` in `.env` remains valid.
