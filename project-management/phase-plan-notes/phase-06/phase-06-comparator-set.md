# Phase 06 — Search Provider Comparator Set

**Generated:** 2026-07-25, Session 14
**Purpose:** Empirical baseline data for designing the Claude-native search provider

## Provider Status

- **Exa:** 402 NO_MORE_CREDITS on all 5 queries (dead since Session 12)
- **Tavily:** 15/15 results returned (free tier)

## Claims Tested

| # | Claim | Type | Expected | Tavily Verdict |
|---|-------|------|----------|----------------|
| 1 | Russia's full-scale invasion of Ukraine occurred in February 2022 | Clear factual | Supported | Supported (scores 0.91–0.95) |
| 2 | ES-11/1 drew 141 votes in favour | Precise number | Supported | **INSUFFICIENT** (scores 0.05–0.09, generic pages) |
| 3 | Support had fallen to 98 votes by Feb 2025 | Planted error (actual: 93) | Refuted | Refuted (two sources say "93", scores 0.90–0.91) |
| 4 | Countries represented nearly half of the world's population | Proportion/nuance | Ambiguous | Likely insufficient (scores 0.38–0.62, indirect sources) |
| 5 | ES-11 voting record includes fifteen resolutions | Countable fact (FALSE: 12 resolutions + 3 amendments) | Refuted | Good sources (scores 0.75–0.82, Wikisource lists resolutions) |

## Tavily Response Structure

Each search returns a dict with keys: `query`, `follow_up_questions`, `answer`, `images`, `results`, `response_time`, `request_id`.

The `answer` field is `None` on the free tier.

Each result has:
- `url` — source URL
- `title` — page title
- `content` — AI-summarized snippet (134 B – 3 KB)
- `raw_content` — full page markdown (0 B – 486 KB; 0 when site blocks scraping)
- `score` — relevance score (0.0–1.0)

The pipeline (`_parse_tavily_results`) prefers `raw_content`, falling back to `content`.

## Content Size Distribution

| Claim | R1 content | R1 raw | R2 content | R2 raw | R3 content | R3 raw |
|-------|-----------|--------|-----------|--------|-----------|--------|
| 1 | 1.4 KB | 480 KB | 1.5 KB | 57 KB | 234 B | 11 KB |
| 2 | 3.0 KB | 486 KB | 1.7 KB | 33 KB | 1.1 KB | 21 KB |
| 3 | 134 B | 3.7 KB | 996 B | 49 KB | 142 B | 0 B |
| 4 | 796 B | 9.8 KB | 140 B | 96 KB | 890 B | 11 KB |
| 5 | 1.3 KB | 186 KB | 1.1 KB | 7 KB | 1.3 KB | 58 KB |

## Key Findings

1. **Raw content is wildly oversized.** Wikipedia pages return 186–486 KB. Evidence summarization (mid tier) is essential. Claude WebFetch can extract targeted sections instead.

2. **Tavily fails on specific entity queries.** Claim 2 (ES-11/1 vote count) returned generic UN pages with scores <0.09. This is Tavily's weakest case.

3. **Refutation works well.** The planted error (98 vs 93 votes) was caught with high confidence by Tavily (and by Exa in Session 8).

4. **Neither provider is optimal.** Exa caps at 2 KB snippets (sometimes too short). Tavily dumps full pages (always too long). A WebSearch + WebFetch pipeline gives control: find URLs, then extract the relevant section.

5. **Exa is dead.** Third session with 402 errors. The Claude-native provider eliminates this dependency.

## Evaluation Metrics for Phase 06

- **Speed:** Single-claim latency, 5-claim parallel throughput, full test-file wall-clock
- **Quality/Accuracy:** Verdict match rate against this baseline (especially claims 2, 3, 5)
- **Cost:** $0 marginal for WebSearch/WebFetch vs $0.007–0.008/search for Exa/Tavily; total LLM token cost per claim

## Raw Data

Full JSON results stored in session scratchpad (`comparator_results.json`). Exa errors: all 402 NO_MORE_CREDITS. Tavily: all 3 results per query.
