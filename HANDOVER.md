# Session Handover

**Last Updated:** 2026-07-23 (Session 4, outgoing)
**Current Status:** Phase 01 IN PROGRESS — one item remaining (01.5.3: `/claimify` skill not tested end-to-end). Phase 02 plan written.

---

## Start Here

**Outgoing session completed:** Emoji fix in `scripts/dev.py`, design discussion on academic verification scope (cited vs citation-free claims, vault integration, cost optimization), Phase 02 plan written (`phase-02-vault-verification-core.md`), first full academic paper PDF test (ukraine working paper, 448 claims, $10 cost — cost analysis recorded), TASKS.md updated, cost CSV cleaned up.

**Incoming session should:**

1. **Test `/claimify` skill end-to-end** (01.5.3). The pipeline works via `run_from_pdf.py` directly (proven Session 4), but the Claude Code `/claimify` skill wrapper has never been exercised. Quick test: start the dev server, then invoke `/claimify workspace/inbox/MS-DRAFT-working-paper-v4.pdf`. Warning: this will spend ~$10 in OpenAI API credit (see cost analysis below).

2. **Review the Phase 02 plan** (`project-management/phase-plans/phase-02-vault-verification-core.md`). It covers vault verification of a markdown draft with wikilink citations — the "best case" scenario using the ukraine working paper as test corpus. The plan was written collaboratively in Session 4 with 8 design pillars agreed. The user should confirm they're happy with the TG breakdown before implementation begins.

3. **Decide whether to begin Phase 02 implementation** or address cost optimization first. The $10/paper cost with current settings may warrant tuning `config.toml` (reduce `max_search_iterations` from 5 to 2–3, reduce `results_per_query`) before running more live tests. See cost analysis in memory and Lesson 11 in the phase plan.

**Phase plan:** `project-management/phase-plans/phase-02-vault-verification-core.md`

---

## Current Context

### Repo structure (post-flatten)

Agent packages at root: `claim_extractor/`, `claim_verifier/`, `fact_checker/`, `utils/`, `security/`, `scripts/`, `ingest/`. No `apps/` directory. `docs/playbook/` for decision rationale.

### Configuration

**`config.toml`** — non-sensitive pipeline config. Sections: `[pipeline]` (llm_provider, search_provider, results_per_query, max_search_iterations), `[models.*]` (tier→model mapping per provider), `[reasoning.*]` (reasoning effort per provider/tier). Environment variables override config.toml values via Pydantic.

**`.env`** — secrets only: `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `EXA_API_KEY`, `TAVILY_API_KEY`, `REDIS_URI`/`REDIS_URL`.

### Environment

| Component | Detail |
|-----------|--------|
| Python | 3.11.15 via uv (`~\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe`) |
| Poetry | 2.4.1 via `uv tool install poetry` |
| Venv | `C:\vpy\claime-agent-j1KWVyi4-py3.11` (short path for Windows MAX_PATH) |
| langgraph-cli | 0.4.8 / langgraph-api 0.4.48 (EOL — upgrade available to 0.11.x, not urgent) |
| Docling models | Cached in `~/.cache/huggingface/` (~505 MB) |
| Dev server | `poetry run dev` (emoji fix applied Session 4) or `poetry run langgraph dev --no-browser --allow-blocking` |

### API keys configured (.env at repo root)

All present: `OPENAI_API_KEY` (sk-proj-, verified live), `EXA_API_KEY` (UUID, verified live), `OPENROUTER_API_KEY` (sk-or-v1, verified live), `TAVILY_API_KEY` (tvly-dev-, verified live), `REDIS_URI` + `REDIS_URL` (both redis://localhost:6379, Redis optional for local dev).

### Model tier mapping (current, from config.toml)

| Tier | OpenAI | OpenRouter | Reasoning |
|------|--------|------------|-----------|
| low | gpt-4o-mini | google/gemma-4-26b-a4b-it | — |
| mid | gpt-4.1-mini | anthropic/claude-haiku-4.5 | — |
| high | gpt-4.1 | anthropic/claude-sonnet-5 | medium |

### What was verified live

| Test | Provider | Search | Result |
|------|----------|--------|--------|
| Session 2 | OpenAI | Exa | 14 claims, 12 supported, 2 refuted |
| Session 3 | OpenRouter | Exa | 2 claims, 2 supported |
| Session 3 | OpenRouter | Tavily | 3 claims, 3 supported |
| Session 4 | OpenAI | Exa | 448 claims (ukraine paper), ~$10 cost |

NOT yet tested: `/claimify` skill end-to-end.

### Key decisions made

1–10: See Session 3 handover (preserved in git history).
11. **Phase 01 PDF test is "does the pipeline run?" (Option 1)** — web search verdicts on academic claims are informational, not authoritative. Vault/literature verification is Phase 02+.
12. **Phase 02 redesigned as "Vault Verification Core"** — replaces old "Argument Chain Verification" concept. Best-case-first strategy: markdown draft with wikilink citations + trusted vault. Phases 03–05 add routing/corpus, deep research commissions, and draft update loop. Edge cases (PDF-only, no vault, missing sources) are backlog items.
13. **Eight design pillars agreed for Phase 02:** claim record not verdict (multi-attribute), run profiles (light/heavy), resource manifest from day one, vault is trusted, wikilink citations only, cite sets with union semantics, positions from day one, batch vault matching.
14. **Cost optimization is a first-class concern.** Three principles: evidence summarization before expensive evaluation, triage-based routing for effort, claim-type-aware method selection (own results → vault, not web). See `memory/feedback_cost_optimization.md`.

### Cost analysis (Session 4)

First full academic paper run: ukraine working paper (7,000 words, 20 sections, 448 claims).

| Model | Tier | Requests | Input tokens | Cost |
|---|---|---|---|---|
| gpt-4o-mini | low | 1,869 | 2.86M | ~$0.47 |
| gpt-4.1 | high | 448 | 3.81M | ~$7.70 |
| gpt-4.1-mini | mid | 4,892 | 3.61M | ~$1.90 |
| **Total** | | **7,209** | **10.27M** | **~$10.07** |

GPT-4.1 is 76% of cost. Each claim gets up to 5 search iterations accumulating evidence, then one GPT-4.1 evaluation call with all evidence (~8,500 tokens average). Config levers: `max_search_iterations` (5→2–3), `results_per_query` (3→2), evidence truncation budget (120K→20–30K tokens in `utils/llm.py:29`).

### Test suite

87 offline tests (`poetry run pytest -q -m "not slow"`). 1 slow test (docling extraction, ~16s with cached models).

| File | Count | Covers |
|------|-------|--------|
| test_models.py | 24 | MODEL_REGISTRY, tier resolution, provider routing, reasoning effort |
| test_settings.py | 13 | Pydantic settings, env var validation |
| test_ingest.py | 31 | PDF extraction, chunking, text dispatch, report rendering |
| test_cost_tracking.py | 12 | Search cost counter, estimates, free-tier balance, print_summary |
| test_config.py | 7 | TOML loading, sections, fallbacks, real config.toml validation |

### Session 4 output files

- `workspace/output/MS-DRAFT-working-paper-v4/results.json` (11MB) — full structured claim records
- `workspace/output/MS-DRAFT-working-paper-v4/report.md` (636KB) — human-readable per-section verdicts
- `workspace/inbox/MS-DRAFT-working-paper-v4.pdf` — the test input (copy of ukraine paper)

All gitignored via `workspace/` patterns.

---

## Recent Sessions

| Date | What was done |
|------|---------------|
| 2026-07-22 | Session 1: Fork, clone, PM setup, assessment artifact, websearch-and-costs doc |
| 2026-07-22 | Session 2: Flatten to agent-only, OpenRouter + tier-based registry, PDF ingest (Docling), /claimify skill, NLTK fix, OpenAI live test, tier rebalancing, model selection playbook, Sonnet 5 hybrid-reasoning correction. 63 tests. 13 commits. |
| 2026-07-23 | Session 3: Reasoning effort fix, search cost tracking, dead export cleanup, config.toml extraction, OpenRouter live test, Exa vs Tavily comparison, architecture audit. 87 tests. 7 commits. |
| 2026-07-23 | Session 4: Emoji fix in dev.py, design discussion on academic verification scope (cited vs citation-free claims, vault structure exploration, doc-rag-backend mapping, cost optimization principles), Phase 02 plan written, first full academic paper PDF test (448 claims, $10 cost with analysis). |
