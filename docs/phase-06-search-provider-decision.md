# Phase 06 — Search Provider Decision Record

**Date:** 2026-07-25 (Session 15)
**Decision:** Defer the search-provider replacement. Buy Exa credits for immediate needs. Build the two-stage provider (SERP + crawl4ai) post-MVP.

## What was decided

1. **The "Claude-native" direction is dead.** Two paths were evaluated and rejected:
   - Anthropic API `web_search` server tool: ~$10/1k searches + result tokens at API rates — more expensive than Exa ($7/1k), defeating the purpose.
   - Headless Claude Code / Agent SDK under the Max subscription: viability at risk — `claude -p` usage is expected to draw from user credits rather than plan allowance (or already does).

2. **Interim (now):** buy Exa credits. Exa's March 2026 pricing ($7/1k with page contents for the first 10 results bundled) is competitive, the integration already exists, and Tavily's free 1,000/month remains the fallback (`search_provider = "tavily"`).

3. **Future (post-MVP): two-stage search provider.** Recorded here so it isn't lost; also recorded in the control-hub vault as an IDEA note against the crawl4ai repo.

## Market scan (July 2026)

| Provider | Price/1k searches | Free tier | Returns content? |
|---|---|---|---|
| Exa | $7 (Mar 2026: content for first 10 results bundled; +$1/1k per result past 10) | $10/mo credit ≈ 1.4k | Yes, full text |
| Tavily | $8 PAYG, $30/mo for 4k | 1,000/month, no card | Yes (oversized raw pages) |
| Serper (Google SERP) | $1 (starter, $50/50k) → $0.30 at scale | 2,500 one-time | No — snippets 150–300 chars |
| Brave | $3–5 | Killed Feb 2026; $5/mo credit ≈ 1k | Snippets only |
| Jina (s.jina.ai) | Token-priced, near-free at our volume | 10M tokens; keyless reader at 20 RPM | Yes, LLM-ready markdown |
| SearXNG (self-hosted) | $0 marginal (Hetzner box exists) | Unlimited | Snippets only |

Structural finding: every cheap option is search-only (URLs + snippets); every content-included option costs $7–8/1k. "Equally good but cheaper" exists only as a **two-stage design**: cheap SERP for URLs, own fetch/extract for evidence text.

Notes: Tavily acquired by Nebius (Feb 2026, pricing stable so far); Jina acquired by Elastic (Oct 2025, direction uncertain); verify whether Serper starter credits expire (~6 months reported) before purchase.

## The deferred design: two-stage provider

```
query → Serper (~$0.001/search, Google-quality SERP, 3 URLs)
      → crawl4ai service (per URL: POST /api/crawl/test, BM25 content_filter
        keyed to query) → relevant markdown → Evidence(url, text, title)
      → [snippet fallback when crawl fails] → existing evaluation pipeline
```

Why this design:

- **Serper fixes the comparator's worst failure.** Claim 2 (ES-11/1 vote count) returned junk on Tavily (scores <0.09); Google handles specific-entity queries well.
- **crawl4ai fixes the content-size problem.** Comparator finding #4: Exa snippets sometimes too short (2 KB cap), Tavily raw pages always too long (186–486 KB). The service's native BM25 `content_filter` returns only query-relevant page blocks — may shrink or replace the mid-tier evidence-summarization call for web evidence.
- **Cost:** ~$1/1k searches + $0 marginal fetch (Railway service already running) vs $7/1k Exa.

### crawl4ai service facts (verified live 2026-07-25)

- Repo `Robs-Git-Hub/crawl4ai-claude-test` (private, v0.56.0, healthy deployment at `crawl4ai-claude-test-production.up.railway.app`, auth `X-API-Key`/`CRAWL4AI_API_KEY`).
- `POST /api/crawl/test`: `{url, test_method, markdown_type, content_filter}` → markdown. Methods escalate baseline → stealth → patchright (default, free) → webshare → residential (WebShare, $3.50/mo).
- Client reference: `crawl4ai-fetcher` skill in `claude-multi-repo-instructions-and-lessons`.

### Known work items for when this is built

1. Load-test crawl4ai concurrency (no browser pooling — each request spawns Chromium ~100–200 MB; safe parallel limit unverified).
2. Client-side semaphore on fetches, independent of routing `Semaphore(5)`.
3. Latency budget: 10–60s/crawl vs ~1s Exa; measure full-file wall-clock in the comparator harness.
4. `CRAWL4AI_API_KEY` + `SERPER_API_KEY` in `.env` + settings validation; graceful degradation to SERP snippets (follow `corpus_client.py` pattern); distinct error-vs-empty logging (402-Exa lesson).
5. Cost tracking entries; `search_provider = "serper-crawl4ai"` (or similar) config case in `_search_query()` dispatch.
6. Evaluate whether BM25-filtered content lets `summarize_evidence` be skipped for this provider.
7. Generalization: the two-stage capability likely belongs partly in the crawl4ai repo (e.g. a `/api/search-and-extract` endpoint) so other projects can reuse it — see control-hub IDEA note.

### Evaluation plan (unchanged from Session 14)

Goal-loop against the 5-claim comparator set (`docs/phase-06-comparator-set.md`): verdict match rate (claims 2, 3, 5 are the discriminators; claim 5 ground truth is **false** — 12 resolutions, not fifteen), speed (single-claim latency, parallel throughput, full-file wall-clock), cost per claim.

## Integration surface (mapped Session 14–15, still valid)

`claim_verifier/nodes/retrieve_evidence.py` (new `SearchProviders` method + dispatch case; note: config is read at module import time — tests monkeypatch module constants), `config.toml`, `utils/cost_tracking.py` (5 hardcoded exa/tavily sites), `utils/settings.py`, `.env.example`. Everything downstream is provider-agnostic.
