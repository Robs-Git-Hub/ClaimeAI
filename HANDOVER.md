# Session Handover

**Last Updated:** 2026-07-22 (Session 2, outgoing)
**Current Status:** Phase 01 IN PROGRESS — TG 01.1–01.5 complete; TG 01.6 partially complete

---

## Start Here

**Outgoing session completed:** Flattened repo to agent-only, added OpenRouter provider with tier-based model registry, added Docling PDF ingest + run_from_pdf CLI, created /claimify skill, fixed NLTK blocking, verified OpenAI provider live (14 claims, 12 supported / 2 refuted), rebalanced OpenRouter tier mapping (Gemma/Haiku/Sonnet), created model selection playbook, corrected Sonnet 5 as hybrid-reasoning model (reasoning level needs setting). 63 offline tests, 13 commits (unpushed).

**Incoming session should:**

1. **Live-test OpenRouter provider.** Set `LLM_PROVIDER=openrouter` in `.env`, run a short fact-check (1–2 claim `.txt` file). This tests the full Gemma 4 → Haiku 4.5 → Sonnet 5 tier chain. **Important:** Sonnet 5 is a hybrid-reasoning model — the reasoning effort level needs to be set when constructing the ChatOpenAI client for the high tier (not yet implemented). Re-confirm OpenRouter model IDs haven't changed.
2. **Live-test Exa vs Tavily.** Swap `search_provider` in `claim_verifier/config/nodes.py` from `"exa"` to `"tavily"`, run the same short test. Compare result quality and speed.
3. **Add search credit/cost tracking.** Build a module that tracks per-run Exa/Tavily API usage (searches made, estimated cost) and reports remaining free tier balance. Exa: $20 initial + $10/month free. Tavily: 1,000 free credits/month.
4. **Test on a real academic paper.** Drop a PDF in `workspace/inbox/`, run `/claimify`. This is the Phase 01 milestone gate.
5. **Push to origin** — 11 commits are local on `main`, nothing pushed yet.

**Phase plan:** `project-management/phase-plans/phase-01-foundation-and-core-pipeline.md`

---

## Current Context

### Repo structure (post-flatten)

Agent packages at root: `claim_extractor/`, `claim_verifier/`, `fact_checker/`, `utils/`, `security/`, `scripts/`, `ingest/`. No `apps/` directory. `docs/playbook/` for decision rationale.

### Environment

| Component | Detail |
|-----------|--------|
| Python | 3.11.15 via uv (`~\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe`) |
| Poetry | 2.4.1 via `uv tool install poetry` |
| Venv | `C:\vpy\claime-agent-j1KWVyi4-py3.11` (short path for Windows MAX_PATH; `poetry.toml` gitignored) |
| langgraph-cli | 0.4.8 / langgraph-api 0.4.48 (pinned to match langgraph 0.4.x; EOL warning cosmetic) |
| Docling models | Cached in `~/.cache/huggingface/` (~505 MB) |
| NLTK punkt_tab | Downloaded; `scripts/dev.py` auto-downloads if missing |
| Dev server | Start with `poetry run dev` (handles NLTK data + `--allow-blocking`) |

### API keys configured (.env at repo root)

All present: `OPENAI_API_KEY` (sk-proj-, verified working), `EXA_API_KEY` (UUID, verified working), `OPENROUTER_API_KEY` (sk-or-v1, not yet live-tested), `TAVILY_API_KEY` (tvly-dev-, not yet live-tested), `LLM_PROVIDER=openai`, `REDIS_URI` + `REDIS_URL` (both redis://localhost:6379, Redis optional for local dev).

### Model tier mapping (current)

| Tier | OpenAI | OpenRouter | Price (in/out per 1M) |
|------|--------|------------|----------------------|
| low | gpt-4o-mini | google/gemma-4-26b-a4b-it | $0.15/$0.60 · $0.06/$0.33 |
| mid | gpt-4.1-mini | anthropic/claude-haiku-4.5 | $0.40/$1.60 · $1/$5 |
| high | gpt-4.1 | anthropic/claude-sonnet-5 | $2/$8 · $2/$10 |

Rationale: `docs/playbook/model-tier-selection.md`

### What was verified live (Session 2)

- OpenAI provider: Apollo 11 paragraph → 14 claims extracted and verified (12 supported, 2 refuted) via Exa search + GPT-4.1 evidence evaluation.
- NOT yet tested: OpenRouter provider, Tavily search, PDF ingest end-to-end with real paper.

### Key decisions made

1. **Keep OpenAI, add OpenRouter** — not a swap, a second option. Tier-based `MODEL_REGISTRY`.
2. **PDF ingest via Docling** (user approved despite transitive torch deps).
3. **Agent README promoted to root** (user approved).
4. **Tier abstraction** (user requested): nodes call `get_llm(tier="low"/"mid"/"high")`, never model names.
5. **OpenRouter rebalancing** (user reviewed): Gemma 4 for low (BYOK), Haiku for mid, Sonnet 5 for high. Opus dropped as over-specced.
6. **Sub-agent model routing** — haiku for exploration/mechanical, sonnet for implementation, top-tier for novel reasoning. Codified in `~/.claude/CLAUDE.md`.
7. **Argument chain verification is Phase 02.**

### Test suite

63 offline tests (`poetry run pytest -q -m "not slow"`). 1 slow test (docling extraction, ~16s with cached models). All added in Session 2.

### Commit history (Session 2, not yet pushed)

| Commit | What |
|--------|------|
| `42e4aae` | docs: update Phase 01 plans from prep findings |
| `9b3bf9b` | refactor: flatten apps/agent to root (TG 01.2) |
| `c36f05a` | chore: add docling and pytest deps |
| `ca24d1e` | feat: OpenRouter integration with MODEL_REGISTRY (TG 01.3) |
| `7122ec8` | feat: Docling PDF ingest + run_from_pdf CLI (TG 01.4) |
| `76bdeb0` | chore: .gitattributes for binary files |
| `cd2b7db` | feat: /claimify skill + md/txt support (TG 01.5) |
| `bc8cf60` | fix: --allow-blocking + NLTK data pre-download |
| `eeb26e9` | refactor: simplify MODEL_REGISTRY from 5 roles to 3 tiers |
| `16f20b2` | refactor: rebalance OpenRouter tiers; add model selection playbook |
| `cae004e` | docs: session 2 wrap |
| `d6285c5` | docs: correct Sonnet 5 as hybrid-reasoning model |

---

## Recent Sessions

| Date | What was done |
|------|---------------|
| 2026-07-22 | Session 1: Fork, clone, PM setup, assessment artifact, websearch-and-costs doc |
| 2026-07-22 | Session 2: Flatten to agent-only, OpenRouter + tier-based registry, PDF ingest (Docling), /claimify skill, NLTK fix, OpenAI live test, tier rebalancing (Gemma/Haiku/Sonnet), model selection playbook, Sonnet 5 hybrid-reasoning correction. 63 offline tests. 13 commits (unpushed). |
