# Web Search Providers and Costs

## Exa AI and Tavily

ClaimeAI uses **Exa AI or Tavily to search the web for evidence** relevant to each extracted factual claim. The selected service returns source links and webpage text, which an LLM then evaluates to determine whether the claim is supported, refuted, conflicting or insufficiently evidenced. ClaimeAI uses one provider at a time, selected via `search_provider` in `config.toml`; the committed default is `exa`. When Exa's credit balance is exhausted (see below), flip the setting to `tavily` locally until Exa's monthly credits refresh or are topped up — Session 12 ran this way after a mid-run exhaustion.

**Exa AI** is a search engine designed specifically for AI systems. Its semantic search can match the meaning of detailed queries rather than relying solely on exact keywords. ClaimeAI uses Exa's neural-search mode and retrieves up to three webpage excerpts for each query.

**Tavily** is a broader web-retrieval service for AI agents. In addition to search, it provides extraction, crawling, site mapping and research tools. Its search API combines web search with filtering, ranking and extraction of content suitable for use by an LLM. In ClaimeAI, Tavily returns up to three results with raw webpage content.

The main practical difference is that **Exa emphasizes semantic search and targeted retrieval**, while **Tavily provides a wider collection of search and web-extraction capabilities**. Either can perform ClaimeAI's evidence-retrieval task, and their output quality should ideally be compared using a representative test set.

### Estimated search costs

ClaimeAI can make between one and five searches for each claim, depending on whether it finds adequate evidence or needs to retry. The estimates below assume pay-as-you-go pricing and exclude the separate cost of the LLM calls used for claim extraction, query generation and evidence evaluation.

| Provider               | Cost per claim | Cost for 50 claims |
| ---------------------- | -------------: | -----------------: |
| Exa standard search    |  $0.007–$0.035 |    **$0.35–$1.75** |
| Tavily basic search    |  $0.008–$0.040 |    **$0.40–$2.00** |
| Tavily advanced search |  $0.016–$0.080 |    **$0.80–$4.00** |

Exa currently charges **$7 per 1,000 standard searches** and provides a **$20 credit at sign-up plus $10 of free credit per month** thereafter. This is a **hard credit cap, not a soft/rate limit** — once exhausted, the API returns HTTP 402 `NO_MORE_CREDITS` and every subsequent search fails outright (observed live on 2026-07-25, mid-run; see Session 12 data below). Exa's per-plan rate limits are a separate, independent constraint from the credit balance. Tavily charges **$0.008 per credit** on pay-as-you-go pricing; basic searches consume one credit and advanced searches consume two. Tavily also provides **1,000 free credits per month**, which is why the project fell back to it after Exa's credits ran out.

These are upper and lower estimates rather than fixed document costs. A claim resolved by the first search costs substantially less than one that uses all five permitted iterations.

> **Fixed (Session 13) — zero-evidence verdicts:** `VerificationResult` now has `INSUFFICIENT` ("Insufficient Information") and `CONFLICTING` ("Conflicting Evidence") members. Empty evidence returns `INSUFFICIENT` without an LLM call at all; an LLM failure or an unparseable verdict also default to `INSUFFICIENT` — previously all three cases silently became `Refuted`. A dead search provider can no longer manufacture a false refutation this way. One gap stays on the backlog: a genuine zero-results search and a search-API error still look identical (both produce empty evidence → `INSUFFICIENT`), so a burst of `Insufficient` verdicts — not `Refuted` — is now the signal to check provider health / search-error logs.

## PixSerp (candidate — evaluated Session 15, not yet integrated)

[PixSerp](https://pixserp.com/) is an AI search API that returns structured, cited answers via an OpenAI-compatible endpoint. Unlike Exa/Tavily which return raw page content, PixSerp returns a **synthesized answer with inline source citations** — each citation carries a URL, title, and kind (web, news, place, etc.). The response follows the OpenAI chat-completions schema (`choices[0].message.content` + `choices[0].message.citations`), making it a potential drop-in via the OpenAI SDK.

### Pricing tiers

PixSerp offers four model tiers, each with different depth/cost tradeoffs. All pricing is flat per-request at any volume.

| Model | Purpose | Cost/1k requests | Cost per claim (1–5 searches) |
|---|---|---|---|
| `pixserp-fast` | Quick cited answer, minimal latency | **$1.50** | $0.0015–$0.0075 |
| `pixserp-standard` | Balanced research — verified key facts | **$2.50** | $0.0025–$0.0125 |
| `pixserp-deep` | Thorough cross-referenced research | **$3.50** | $0.0035–$0.0175 |
| `pixserp-agent` | Multi-step research loop in one call — search, scrape, follow links, cross-check | **$3.50/step** | Variable (per-step) |

Free tier: **$2.50 credit** on signup (no card required, never expires) — enough for ~1,667 fast-tier or ~714 standard-tier searches. No monthly refresh.

For comparison: Exa is $7/1k, Tavily is $8/1k. Even `pixserp-deep` at $3.50/1k is half the cost of Exa with content included.

The `pixserp-agent` tier is architecturally different — it runs a multi-step research loop (search, scrape, follow links, cross-check) within a single API call, billed per step at $0.0035/step. This is closest to what our two-stage Serper+crawl4ai design would do manually, but managed by PixSerp. Worth evaluating separately from the standard search tiers.

### Session 15 live test (2026-07-25)

Ran 5 comparator claims (from `phase-06-comparator-set.md`) against `pixserp-web` (likely maps to `pixserp-fast` tier). Query format: `"Verify this factual claim and provide evidence for or against it: {claim}"`.

| Claim | Expected | PixSerp Result | Citations | Latency | Tokens |
|---|---|---|---|---|---|
| 1: Russia invasion Feb 2022 | Supported | **Supported** — Reuters, UN News | 2 | 1.6s | 12,179 |
| 2: ES-11/1 drew 141 votes | Supported | **Supported** — 3 sources cite "141" | 3 | 1.3s | 9,868 |
| 3: 98 votes Feb 2025 (planted error, actual: 93) | Refuted | **Weak refute** — "not supported" but no counter-figure | 0 | 3.4s | 6,862 |
| 4: Nearly half world's population | Ambiguous | **Supported** — percentage reasoning | 1 | 1.8s | 11,546 |
| 5: Fifteen resolutions (false: 12 + 3 amendments) | Refuted | **Unsubstantiated** — found only ES-11/1 | 1 | 1.4s | 9,923 |

**Key findings vs Tavily baseline:**
- **Claim 2 (specific-entity query): PixSerp wins decisively.** Three independent sources all citing "141 votes". Tavily completely failed this query class (scores <0.09, generic UN pages).
- **Claim 3 (planted error): Tavily wins.** Tavily found two sources explicitly stating "93" (scores 0.90–0.91), enabling a clear Refuted verdict. PixSerp found no counter-evidence — "not supported" would yield INSUFFICIENT, not Refuted, in our pipeline.
- **Claim 5 (countable fact): Neither excels.** Tavily found Wikisource (scores 0.75–0.82); PixSerp found only ES-11/1. Both would need iterative search.

**Verdict:** complementary strengths — PixSerp handles specific entities well; Tavily handles refutation with counter-evidence well. Neither is a solo replacement for all cases. See `project-management/phase-plan-notes/phase-06/phase-06-search-provider-decision.md` for integration options and the deferred two-stage design.

### Integration notes

PixSerp returns **synthesized answers**, not raw page content. This differs from Exa (raw text snippets) and Tavily (raw page markdown). Integration options for our pipeline:

1. **Use PixSerp's answer as `Evidence.text`** — simplest; the high-tier evaluator receives pre-synthesized content rather than raw source material. Risk: double-synthesis (PixSerp synthesizes, then our evaluator re-evaluates).
2. **Use cited URLs + fetch stage** (crawl4ai or httpx) for raw content — preserves evaluation integrity but adds complexity and latency.
3. **Use `pixserp-agent` tier** which does its own multi-step research loop — the closest match to our pipeline's iterative search, but delegates control entirely to PixSerp.

The `pixserp-standard` or `pixserp-deep` tiers might produce stronger refutation evidence (claim 3) than `pixserp-fast` — worth testing before ruling PixSerp out for that case. The `pixserp-agent` tier could potentially replace our entire search+evaluate loop for web claims.

### Corpus route costs

The corpus route (Phase 04–05, `ingest/corpus_route.py`) searches the self-hosted doc-rag-backend (`api.ragtogo.com`) instead of the public web. Because ClaimeAI is the first client of that backend, **marginal search cost is effectively $0** — there is no per-request charge like Exa or Tavily.

Cost is therefore driven almost entirely by LLM calls, not search:

| Step | Tier | Notes |
| --- | --- | --- |
| Evidence summarization | mid | condenses retrieved passages before evaluation |
| Route-local evaluation | high | produces `corpus_supported` / `corpus_contradicted` / `corpus_insufficient` / `no_corpus_hits` |

Combined, this comes to roughly **$0.01–$0.02 per claim** in LLM cost. Unlike the web route, the corpus route makes a **single search per claim with no retry/iteration loop** (the web route's up-to-five-iteration retry logic does not apply here), so the corpus route's cost profile is both cheaper and flatter than web search.

## LLM costs

LLM usage is driven by the three-tier model mapping in `MODEL_REGISTRY` (`utils/models.py`). See `docs/playbook/model-tier-selection.md` for full rationale. Approximate list prices per million tokens (input / output):

| Tier | OpenAI model | ~$/M in/out | OpenRouter model | ~$/M in/out |
| --- | --- | --- | --- | --- |
| low (extraction) | `gpt-4o-mini` | $0.15 / $0.60 | `google/gemma-4-26b-a4b-it` | $0.06 / $0.33 |
| mid (query gen, search decision) | `gpt-4.1-mini` | $0.40 / $1.60 | `anthropic/claude-haiku-4.5` | $1 / $5 |
| high (evidence evaluation) | `gpt-4.1` | $2 / $8 | `anthropic/claude-sonnet-5` | $2 / $10 |

Rough order of magnitude per document: extraction makes 3 voting completions per sentence for two stages plus decomposition/validation on small prompts (typically cents), while evidence evaluation runs once per claim over up to ~15 retrieved snippets — this is the dominant LLM cost.

> Prices checked against openrouter.ai on 2026-07-22. OpenAI prices are approximate and **need confirmation against openai.com/pricing** before budgeting. OpenRouter pricing shown is standard; BYOK pricing may differ.

> **D10 cost impact (Session 12 amendment; recalibrated Session 13):** the routing cascade sends any vault- or corpus-supported claim with `importance >= cross_check_importance_threshold` through one additional independent **web confirmation check** — previously, supported verdicts were never re-checked against the web at all. Controlled by `support_confirmation` in `config.toml` (default `true`); the threshold itself is now a `config.toml` `[pipeline]` key, `cross_check_importance_threshold` (default `4`, unchanged behavior — raise to `5` to tighten cost control). Session 12's estimate assumed importance clustered at 4+ on roughly 14 of 17 standard-test-file claims, i.e. web-call volume "roughly doubling." Session 13's anchored 1–5 rubric — plus a core-data carve-out that keeps quantitative claims reporting the draft's central data (e.g. vote tallies) at 4 — brought a live spot-check down to **12 of 17** claims at importance ≥ 4, so expect somewhat less D10 volume than the original estimate, while the tally carve-out preserves D10 coverage for the planted-error scenario it exists to catch.

## Live run data — Session 12 (2026-07-25)

Two live heavy-profile runs against real vault content, captured after the corpus route and D10 confirmation check landed.

**Cited-file milestone run (Exa)** — 16 claims: 8 vault-resolved, 4 corpus-routed, 4 web-routed (including at least one corpus→web cascade, where a silent corpus verdict fell through to web search). Wall-clock time ~2 minutes. The Exa search-cost counter (`utils/cost_tracking.py`) logged 18+ searches for roughly **$0.13** total — consistent with the per-claim estimates above once corpus routing (zero marginal search cost) and D10 confirmation checks are accounted for. This run's search volume is what eventually exhausted Exa's credit balance (see the `NO_MORE_CREDITS` note above).

**Conflict-demo run (Tavily)** — 9 claims, all vault-resolved, triggering 9 D10 web-confirmation checks (importance ≥ 4 across the board). Evidence summarization had a dramatic effect on Tavily's raw content volume: one claim's raw evidence was **3.6 MB**, compressed to **139 KB** after mid-tier summarization — a 96–99% reduction — before being passed to the high-tier evaluator. This confirms the summarization step is essential for keeping high-tier evaluation prompts (and cost) bounded when using Tavily, which tends to return much bulkier raw page content than Exa.
