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
