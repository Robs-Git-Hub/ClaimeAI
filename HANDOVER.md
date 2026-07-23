# Session Handover

**Last Updated:** 2026-07-23 (Session 3, outgoing)
**Current Status:** Phase 01 NEARLY COMPLETE — all code and live provider/search tests done; real academic paper PDF test deferred pending design discussion on verification scope

---

## Start Here

**Outgoing session completed:** Reasoning effort for Sonnet 5 (REASONING_CONFIG + ChatOpenAI built-in param), search cost tracking module (call-count-based with INFO logging), dead export cleanup, config.toml extraction (secrets in .env, config in config.toml), OpenRouter live test (2 claims, 2 supported via Gemma→Haiku→Sonnet 5), Exa vs Tavily comparison (both produce correct verdicts; Tavily returns ~35× more raw content), architecture audit (clean), completion review with fixes. 87 offline tests, 4 commits (unpushed).

**Incoming session should:**

1. **Push to origin.** 4 commits on `main`, not yet pushed.

2. **Design discussion: verification scope for academic papers.** Before running 01.6.1d (real paper PDF test), the user wants to discuss what "success" looks like. The current pipeline verifies claims against web search — this works for factual claims but academic papers need literature-corpus verification. The user has several routes into the literature corpus that should be considered:
   - **PRISMA search tools** — systematic review infrastructure (massive undertakings)
   - **OpenAlex and Google Scholar sub-tools** — simpler academic search
   - **doc-to-RAG pipeline** — ingest select sets of academic papers into RAGable databases relevant to a claim search
   - **Obsidian vaults with argument chains** — distilled notes (SOURCE-, QUOTE-, PARA-, CLAIM-, THESIS-) from the literature
   
   This is a design question that affects Phase 01 scope (is the PDF test just "does the pipeline run?" or "does it produce useful academic verification?") and Phase 02 planning (argument chain verification was always planned, but the literature search tools expand the picture).

3. **Run the academic paper PDF test** (01.6.1d) once the verification scope is agreed. Drop a PDF in `workspace/inbox/`, start the server, run `poetry run python scripts/run_from_pdf.py <path>`.

4. **Fix the `scripts/dev.py` emoji encoding issue.** The rocket emoji (🚀) in the print statement causes `UnicodeEncodeError` on Windows cp1252. Quick fix: remove the emoji or set `PYTHONIOENCODING=utf-8`. Current workaround: run `poetry run langgraph dev --no-browser --allow-blocking` directly.

**Phase plan:** `project-management/phase-plans/phase-01-foundation-and-core-pipeline.md`

---

## Current Context

### Repo structure (post-flatten)

Agent packages at root: `claim_extractor/`, `claim_verifier/`, `fact_checker/`, `utils/`, `security/`, `scripts/`, `ingest/`. No `apps/` directory. `docs/playbook/` for decision rationale.

### Configuration

**`config.toml`** (new in Session 3) — non-sensitive pipeline config. Sections: `[pipeline]` (llm_provider, search_provider, results_per_query, max_search_iterations), `[models.*]` (tier→model mapping per provider), `[reasoning.*]` (reasoning effort per provider/tier). Environment variables override config.toml values via Pydantic.

**`.env`** — secrets only: `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `EXA_API_KEY`, `TAVILY_API_KEY`, `REDIS_URI`/`REDIS_URL`. `LLM_PROVIDER` removed from `.env` — now in `config.toml`.

### Environment

| Component | Detail |
|-----------|--------|
| Python | 3.11.15 via uv (`~\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe`) |
| Poetry | 2.4.1 via `uv tool install poetry` |
| Venv | `C:\vpy\claime-agent-j1KWVyi4-py3.11` (short path for Windows MAX_PATH) |
| langgraph-cli | 0.4.8 / langgraph-api 0.4.48 |
| Docling models | Cached in `~/.cache/huggingface/` (~505 MB) |
| Dev server | `poetry run langgraph dev --no-browser --allow-blocking` (NOT `poetry run dev` — emoji crash on Windows) |

### API keys configured (.env at repo root)

All present: `OPENAI_API_KEY` (sk-proj-, verified live), `EXA_API_KEY` (UUID, verified live), `OPENROUTER_API_KEY` (sk-or-v1, verified live), `TAVILY_API_KEY` (tvly-dev-, verified live), `REDIS_URI` + `REDIS_URL` (both redis://localhost:6379, Redis optional for local dev).

### Model tier mapping (current, from config.toml)

| Tier | OpenAI | OpenRouter | Reasoning |
|------|--------|------------|-----------|
| low | gpt-4o-mini | google/gemma-4-26b-a4b-it | — |
| mid | gpt-4.1-mini | anthropic/claude-haiku-4.5 | — |
| high | gpt-4.1 | anthropic/claude-sonnet-5 | medium |

OpenRouter IDs verified against openrouter.ai on 2026-07-23.

### What was verified live

| Test | Provider | Search | Result |
|------|----------|--------|--------|
| Session 2 | OpenAI | Exa | 14 claims, 12 supported, 2 refuted |
| Session 3 | OpenRouter | Exa | 2 claims, 2 supported |
| Session 3 | OpenRouter | Tavily | 3 claims, 3 supported |

NOT yet tested: real academic paper PDF, /claimify skill end-to-end.

### Key decisions made

1–6: See Session 2 handover (preserved in git history).
7. **Argument chain verification is Phase 02.**
8. **config.toml for non-sensitive config** (user-requested, Session 3): `.env` for secrets only, `config.toml` for provider selection, model mappings, search config, reasoning effort. Python `tomllib` (built-in 3.11+). Env vars override via Pydantic.
9. **Simple call-counter for cost tracking** (Session 3 system-thinking): No class, no generic operations. Langchain wrappers don't expose response metadata. Process-local counters with INFO logging — costs visible in server terminal, not in the client script.
10. **Academic paper verification needs design discussion** (Session 3, user-raised): Current pipeline verifies against web search. Academic papers need literature-corpus verification. User has PRISMA tools, OpenAlex/Scholar sub-tools, doc-to-RAG pipeline, and Obsidian argument chain vaults. This expands the picture beyond Phase 01's web-search scope and connects to Phase 02's argument chain verification.

### Test suite

87 offline tests (`poetry run pytest -q -m "not slow"`). 1 slow test (docling extraction, ~16s with cached models).

| File | Count | Covers |
|------|-------|--------|
| test_models.py | 24 | MODEL_REGISTRY, tier resolution, provider routing, reasoning effort |
| test_settings.py | 13 | Pydantic settings, env var validation |
| test_ingest.py | 31 | PDF extraction, chunking, text dispatch, report rendering |
| test_cost_tracking.py | 12 | Search cost counter, estimates, free-tier balance, print_summary |
| test_config.py | 7 | TOML loading, sections, fallbacks, real config.toml validation |

### Commit history (Session 3, not yet pushed)

| Commit | What |
|--------|------|
| `0dacdbf` | feat: reasoning effort + cost tracking + dead export cleanup |
| `365eace` | docs: TASKS and phase plan for Session 3 |
| `f18b1ca` | docs: reasoning effort future→implemented, fix stale mapping |
| `7adc896` | refactor: config.toml extraction |

---

## Recent Sessions

| Date | What was done |
|------|---------------|
| 2026-07-22 | Session 1: Fork, clone, PM setup, assessment artifact, websearch-and-costs doc |
| 2026-07-22 | Session 2: Flatten to agent-only, OpenRouter + tier-based registry, PDF ingest (Docling), /claimify skill, NLTK fix, OpenAI live test, tier rebalancing, model selection playbook, Sonnet 5 hybrid-reasoning correction. 63 tests. 13 commits. |
| 2026-07-23 | Session 3: Reasoning effort fix (REASONING_CONFIG + ChatOpenAI built-in), search cost tracking (call-counter with logging), dead export cleanup, config.toml extraction (.env→secrets only), OpenRouter live test (passed), Exa vs Tavily comparison (both passed), architecture audit (clean), completion review. 87 tests. 4 commits (unpushed). |
