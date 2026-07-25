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

Structural finding: most cheap options are search-only (URLs + snippets); most content-included options cost $7–8/1k. The exception is **PixSerp** — see below.

Notes: Tavily acquired by Nebius (Feb 2026, pricing stable so far); Jina acquired by Elastic (Oct 2025, direction uncertain); verify whether Serper starter credits expire (~6 months reported) before purchase. Bing Search APIs retired August 2025 — no longer an option.

### PixSerp — late discovery (Session 15, not yet evaluated)

[pixserp.com](https://pixserp.com/) — a content-included search API at $1.50/1k, potentially a single-stage drop-in:

| Feature | PixSerp | Exa (current) |
|---|---|---|
| Price/1k | **$1.50 flat** at any volume | $7 |
| Free tier | **$2.50 credit** (never expires) ≈ 1,667 searches | $10/mo ≈ 1,400 |
| Returns content | Yes — structured JSON with cited sources, every claim carries its source URL | Yes — full text (2 KB cap) |
| LLM integration | OpenAI-compatible endpoint (drop-in SDK swap); MCP server (Claude Code, Cursor); JSON schema output | LangChain wrapper only |
| Verticals | 10: web, news, images, places, shopping, flights, hotels, YouTube, transcripts, any URL | Web (neural/keyword) |
| Rate limits | Unknown — needs testing | Tier-based |

**Why this matters:** At $1.50/1k with structured content, PixSerp could be a **single-stage replacement** — no Serper+crawl4ai two-stage needed. The structured JSON with source URLs maps almost directly to `Evidence(url, text, title)`. The MCP server also means it could be used from Claude Code sessions directly.

**What's unknown and must be tested before committing:**
1. **Content quality for fact-checking:** Does it return enough text to evaluate claims (our pipeline needs substantive evidence, not one-sentence answers)? Run the 5-claim comparator.
2. **Specific-entity queries:** Claim 2 (ES-11/1 vote count) is the discriminator — Tavily failed this class of query badly.
3. **Latency** — the $1.50 price point might come with higher latency.
4. **Service maturity and reliability** — relatively new (Product Hunt launch); evaluate uptime and error handling.
5. **How the "ten answer shapes" interact** — do we control which shape we get, or does it auto-select?
6. **Whether the OpenAI-compatible response maps cleanly** to our `Evidence` schema without a parsing layer.

**Recommendation:** Sign up (free, no card), run the comparator claims through it, and compare against the Tavily baseline in `phase-06-comparator-set.md`. If it matches or beats Tavily on verdict accuracy for claims 2/3/5, it becomes the primary candidate — simpler than the two-stage Serper+crawl4ai build and 4.7× cheaper than Exa.

### PixSerp comparator results (Session 15 live test, 2026-07-25)

Ran all 5 claims against `pixserp-web` model via OpenAI-compatible endpoint. Query format: `"Verify this factual claim and provide evidence for or against it: {claim}"`.

| Claim | Expected | PixSerp Result | Citations | Latency | Tokens |
|---|---|---|---|---|---|
| 1: Russia invasion Feb 2022 | Supported | **Supported** — Reuters, UN News sources | 2 | 1.6s | 12,179 |
| 2: ES-11/1 drew 141 votes | Supported | **Supported** — 3 independent sources all cite "141" | 3 | 1.3s | 9,868 |
| 3: 98 votes by Feb 2025 (planted error) | Refuted | **Weak refute** — "not supported by evidence" but no counter-figure found | 0 | 3.4s | 6,862 |
| 4: Nearly half world's population | Ambiguous | **Supported** — percentage reasoning from G20 analysis | 1 | 1.8s | 11,546 |
| 5: Fifteen resolutions (false) | Refuted | **Unsubstantiated** — found only ES-11/1, not full list | 1 | 1.4s | 9,923 |

**Comparison vs Tavily baseline (from phase-06-comparator-set.md):**

- **Claim 2 (discriminator): PixSerp wins decisively.** Three sources with the exact "141 votes" figure. Tavily completely failed (scores <0.09, generic pages). This was the hardest query in the set.
- **Claim 3 (discriminator): Tavily wins.** Tavily found two sources explicitly stating "93 votes" (scores 0.90–0.91), enabling a clear Refuted verdict. PixSerp found no counter-evidence — only "not supported", which would likely yield INSUFFICIENT rather than Refuted in our pipeline.
- **Claim 5 (discriminator): Neither excels.** Tavily found Wikisource listing resolutions (scores 0.75–0.82); PixSerp found only ES-11/1 and couldn't count the full set. Both would need iterative search to get the definitive answer.

**Response structure:**
```json
{
  "choices": [{"message": {"role": "assistant", "content": "...", "citations": [
    {"kind": "web", "url": "...", "title": "..."}
  ]}}],
  "usage": {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N}
}
```

Key design note: PixSerp returns a **synthesized answer with inline citations**, not raw page content. Our pipeline feeds raw evidence text to a high-tier evaluator. Integration options:
- (a) Use PixSerp's answer text as the `Evidence.text` field — simplest drop-in, but the evaluator receives pre-synthesized content rather than raw source material.
- (b) Use cited URLs + a fetch stage (crawl4ai or httpx) to get raw content — preserves evaluation integrity but adds complexity and latency.
- (c) Trust PixSerp's synthesis and restructure the evaluation prompt — biggest architectural change, highest risk.

Option (a) is recommended for a first spike; option (b) as a fallback if evaluation quality degrades.

**Verdict: PixSerp is a strong candidate but not a clear winner.** Its strength (specific-entity queries) is Tavily's weakness, and vice versa (planted-error refutation). A dual-provider strategy — PixSerp primary, Tavily fallback for refutation confirmation — or iterative search (PixSerp first pass, Tavily if INSUFFICIENT) may outperform either alone. Both are dramatically cheaper than Exa.

### Matrix test: tiers × prompt styles (Session 15, 27 calls)

Tested 3 discriminator claims × 3 tiers (`pixserp-fast`, `pixserp-standard`, `pixserp-deep`) × 3 prompt phrasings:
- **verify**: `"Verify this factual claim and provide evidence for or against it: {claim}"` (original)
- **facts**: `"What are the facts about: {claim}"` (neutral, retrieves context)
- **query**: keyword-style query matching what our pipeline's mid-tier query generator produces (e.g. `"UN General Assembly Ukraine resolution votes February 2025 how many"`)

**Claim 2 (ES-11/1, 141 votes — expected: Supported):** All 9 combinations found "141" with 2–3 citations. Prompt style and tier make no difference on this claim — PixSerp handles specific-entity queries reliably regardless of phrasing.

**Claim 3 (98 votes planted error — expected: Refuted):** This is where the dials matter:
- **verify** style (all tiers): Says "not supported by evidence" with zero citations — correctly doubts the claim but provides no counter-figure. Our evaluator would produce INSUFFICIENT, not Refuted.
- **facts** style + deep tier: **Confirmed the claim as having 98 votes** with 3 authoritative news citations (Le Monde, WashPost, Al Jazeera). This is actually a more complex finding: the February 2025 UNGA session had multiple resolutions voted on the same day, and one resolution (A/RES/ES-11/9) did reportedly receive ~98 votes. The "planted error" in our test file may be conflating two different resolutions — the claim says "support had fallen to 98" generically, and PixSerp found sources reporting 98 for one specific resolution. This raises questions about whether our ground truth for claim 3 needs revisiting.
- **query** style + deep tier: Found the same authoritative sources but reported "141" — the keyword query led it to the ES-11/1 figure from 2022, not the February 2025 vote. Keyword queries are the **worst** prompt style for temporal disambiguation.

**Claim 5 (fifteen resolutions — expected: Refuted):** No tier/prompt combination found the actual list of ES-11 resolutions or the correct count (12 resolutions + 3 amendments). The deep tier + facts style **hallucinated confirmation** ("the record shows that the package contains fifteen individual resolutions"), citing an irrelevant SEC filing. This is a clear quality concern — PixSerp synthesized a confident wrong answer from irrelevant sources.

**Key conclusions from the matrix:**

1. **Prompt style matters more than tier for factual claims.** The "facts" style consistently retrieved more substantive content than "verify" (which biases toward confirmation/denial). The "query" keyword style is worst for temporal queries (confuses time periods).
2. **Higher tiers don't reliably improve accuracy.** `pixserp-deep` hallucinated on claim 5 and confirmed the "98 votes" figure on claim 3 (which may or may not be an error — see above). The tier mainly affects depth of retrieval, not correctness.
3. **PixSerp's synthesized output is a liability for fact-checking.** When the underlying sources are ambiguous or the query is poorly specified, PixSerp confidently synthesizes a wrong answer rather than surfacing the ambiguity. Raw-evidence providers (Exa/Tavily) at least let our high-tier evaluator see the source material and judge for itself.
4. **Claim 3 ground truth needs investigation.** If the February 2025 UNGA session genuinely had a resolution with ~98 votes, our test file's "planted error (actual: 93)" annotation may be wrong or at least ambiguous. This should be verified against official UN voting records before using claim 3 as a discriminator.

## External benchmark: RAGAS context-quality evaluation (2024)

**Source:** [Context is King — Evaluating real-time LLM context quality with Ragas](https://emergentmethods.medium.com/context-is-king-evaluating-real-time-llm-context-quality-with-ragas-a8df8e815dc9) (Emergent Methods, June 2024)

Benchmarked AskNews, JinaAI, Tavily, and Exa on 8 queries across 4 categories (latest news, general web, knowledge search, "Google-esque") using RAGAS metrics:

| Metric | Winner | Detail |
|---|---|---|
| Answer correctness | AskNews | 40% better than Tavily |
| Context precision | AskNews | 78% improvement vs JinaAI |
| Retrieval speed | AskNews | 0.43s (vs JinaAI 8.1s, others 1–3s) |
| Input tokens (cost) | JinaAI | Smallest context; AskNews 3rd (15% premium) |

**Status (July 2026):** Not rerun or updated. No equivalent RAGAS-based benchmark found for the current provider landscape (Serper, Brave, etc. untested by this method). The code is open-source (Google Colab notebook, contact `emergentmethods.ai`) — a self-run version against current providers + our two-stage design would be a useful validation when the build happens.

**Relevance to our evaluation plan:** Our 5-claim comparator set tests a narrower but deeper question (fact-checking verdict accuracy, not general context quality), and the RAGAS methodology could complement it — especially `context_precision` and `answer_correctness` as metrics alongside our verdict-match rate. Consider running both when building the two-stage provider.

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

Goal-loop against the 5-claim comparator set (`project-management/phase-plan-notes/phase-06/phase-06-comparator-set.md`): verdict match rate (claims 2, 3, 5 are the discriminators; claim 5 ground truth is **false** — 12 resolutions, not fifteen), speed (single-claim latency, parallel throughput, full-file wall-clock), cost per claim.

## Integration surface (mapped Session 14–15, still valid)

`claim_verifier/nodes/retrieve_evidence.py` (new `SearchProviders` method + dispatch case; note: config is read at module import time — tests monkeypatch module constants), `config.toml`, `utils/cost_tracking.py` (5 hardcoded exa/tavily sites), `utils/settings.py`, `.env.example`. Everything downstream is provider-agnostic.
