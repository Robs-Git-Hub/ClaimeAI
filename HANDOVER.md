# Session Handover

**Last Updated:** 2026-07-22 (Session 2)
**Current Status:** Phase 01 IN PROGRESS — TG 01.1–01.5 complete; TG 01.6 partially complete (OpenAI live test passed; OpenRouter live test and real-paper test remain)

---

## Start Here

**Session 2 completed:** Flattened repo to agent-only (TG 01.2), added OpenRouter as second LLM provider with per-role model registry (TG 01.3), added Docling PDF ingest module + run_from_pdf CLI (TG 01.4), created /claimify Claude Code skill (TG 01.5). Fixed NLTK blocking issue in dev server. Verified live: OpenAI provider, 14 claims extracted and verified from Apollo 11 paragraph.

**Incoming session should:**

1. **Test OpenRouter provider live** (task 01.3.5). Set `LLM_PROVIDER=openrouter` in .env, run a short fact-check. Re-confirm model IDs match what OpenRouter currently serves (verified 2026-07-22: `anthropic/claude-haiku-4.5`, `anthropic/claude-sonnet-5`, `anthropic/claude-opus-4.8`).
2. **Test on a real academic paper** (task 01.4.7 / 01.6.1). Drop a PDF in `workspace/inbox/` and run `/claimify`.
3. **Push to origin** (task 01.6.3). All commits are local; nothing has been pushed yet this session.
4. **Phase 02 design** if Phase 01 is closed — argument chain verification (integrates with Obsidian vault argument pyramids from article-writer-research-of-agents).

**Phase plan:** `project-management/phase-plans/phase-01-foundation-and-core-pipeline.md`

---

## Current Context

### Repo structure (post-flatten)

Agent packages are at root: `claim_extractor/`, `claim_verifier/`, `fact_checker/`, `utils/`, `security/`, `scripts/`, `ingest/`. No more `apps/` directory, no web frontend, no Chrome extension.

### Environment

- **Python:** 3.11.15 via uv (`C:\Users\rj_co\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe`)
- **Poetry:** 2.4.1 via `uv tool install poetry`
- **Venv:** `C:\vpy\claime-agent-j1KWVyi4-py3.11` (short path to dodge Windows MAX_PATH — long paths disabled, no admin). Configured via repo-local `poetry.toml` (gitignored).
- **langgraph-cli:** 0.4.8 / langgraph-api 0.4.48 pinned in venv (matches langgraph 0.4.x project pins; EOL warning is cosmetic)
- **Docling models:** cached in `~/.cache/huggingface/` (~505 MB, first-run download completed in Session 2)
- **NLTK punkt_tab:** downloaded; `scripts/dev.py` auto-downloads if missing
- **Dev server:** must start with `poetry run dev` (or `langgraph dev --no-browser --allow-blocking`) — NLTK's synchronous tokenizer requires `--allow-blocking`
- **.env:** OPENAI_API_KEY, EXA_API_KEY, OPENROUTER_API_KEY, TAVILY_API_KEY, LLM_PROVIDER=openai, REDIS_URI, REDIS_URL all set

### API keys configured

- `OPENAI_API_KEY` — `sk-proj-` prefix, verified working
- `EXA_API_KEY` — UUID format, verified working
- `OPENROUTER_API_KEY` — `sk-or-v1` prefix, not yet live-tested
- `TAVILY_API_KEY` — `tvly-dev-` prefix, not yet live-tested
- `REDIS_URI` / `REDIS_URL` — both set to `redis://localhost:6379` (Redis optional for local dev)

### What was verified live (Session 2)

- OpenAI provider: Apollo 11 paragraph → 14 claims extracted and verified (12 supported, 2 refuted) via Exa search + GPT-4.1 evidence evaluation. Pipeline takes ~2–3 minutes for a short paragraph.

### Key decisions made

1. **Keep OpenAI, add OpenRouter** — not a swap, a second option. Per-role MODEL_REGISTRY in `utils/models.py`.
2. **PDF ingest via Docling** (user approved despite transitive torch deps — they're used deps of a real feature). Doc-rag-backend investigation deferred.
3. **Agent README promoted to root** (user approved). INSTALLATION.md rewritten agent-only.
4. **Argument chain verification is Phase 02** — integrates with Obsidian vault argument pyramids from article-writer-research-of-agents.
5. **Sub-agent model routing** — haiku for exploration/mechanical, sonnet for implementation, top-tier for novel reasoning only. Codified in `~/.claude/CLAUDE.md`.

### Related repos

- **doc-rag-backend** — Docling PDF extraction (Mac only, not cloned on Windows)
- **article-writer-research-of-agents** — argument pyramid pipeline (Phase 02 integration point)
- **control-hub-building** — REPO note at `REPO-ClaimeAI.md`

### Test suite

63 offline tests passing (pytest, `poetry run pytest -q -m "not slow"`). 1 slow test (docling extraction with cached models, ~16s). No tests existed upstream — all added in Session 2.

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

---

## Recent Sessions

| Date       | What was done |
|------------|---------------|
| 2026-07-22 | Session 1: Fork, clone, PM setup, assessment artifact, websearch-and-costs doc |
| 2026-07-22 | Session 2: Flatten to agent-only (TG 01.2), OpenRouter integration (TG 01.3), PDF ingest (TG 01.4), /claimify skill (TG 01.5), NLTK fix, OpenAI live test passed. 63 offline tests. 8 commits (unpushed). |
