# Phase 01: Foundation & Core Pipeline

**Status:** COMPLETE (Session 5, 2026-07-23)
**Started:** 2026-07-22
**Goal:** Transform the ClaimeAI fork from a full-stack monorepo into a lean, CLI-driven fact-checking tool with PDF ingestion and a Claude Code skill.

---

## Context

ClaimeAI was forked from BharathxD/ClaimeAI — a LangGraph-based fact-checking system with a Next.js frontend, Chrome extension, and Python agent backend. The agent backend is the only valuable part for our use case: extracting factual claims from text and verifying them against web evidence.

The fork needs to be stripped to the agent only, given PDF input capability (reusing the Docling process from doc-rag-backend), and wrapped in a `/claimify` skill for Claude Code orchestration. OpenRouter support is added alongside the existing OpenAI integration to provide model flexibility.

## Dependencies

- **doc-rag-backend** (Mac only) — Docling PDF extraction process. TG 01.4 requires investigating this on Mac to understand the sentence/span output format.
- **OpenRouter API key** — needed for TG 01.3 testing.
- **Exa AI API key** — needed for web search in the verification pipeline.
- **Redis** — needed for LangGraph. Run via Docker: `docker run -p 6379:6379 redis/redis-stack-server:6.2.6-v17`

## Task Groups

### TG 01.1: PM Structure ✓

Set up CLAUDE.md, HANDOVER.md, project-management directory, REPO note in control hub. This is done.

### TG 01.2: Strip to Agent-Only

Remove the Next.js web app (`apps/web/`), Chrome extension (`apps/extension/`), and Turborepo orchestration. Flatten `apps/agent/*` to the repo root. Remove all unused ML dependencies (torch, transformers, sentence-transformers, huggingface-hub, scikit-learn, scipy, numpy) — prep confirmed zero imports for all of them; nltk stays (used by the sentence splitter).

**Prep findings (Session 2) that de-risk the flatten:**
- All Python imports are absolute top-level package imports; no `sys.path` hacks or relative paths anywhere. `langgraph.json` graph paths are relative to its own location. **No import rewrites needed** — move files and go.
- `.env` loading is CWD-relative (both `load_dotenv()` and pydantic-settings), so `.env` just moves to root.
- **`apps/web/docker-compose.yml` provides the agent's Redis/Postgres stack** — relocate a slimmed version to root BEFORE deleting `apps/web/`.
- pyproject cleanup needed: `security` package missing from `packages` list (but imported); dangling `create-run` script entry points at a nonexistent file.
- Redis is optional for local dev — only the dormant API-key auth flow uses it (`langgraph.json` has no `auth` key).
- **Decision (user-approved):** promote `apps/agent/README.md` to root README with fork framing, rather than patching the stale monorepo README.

**Verification (no test suite exists upstream):** goal is all three packages import cleanly and all three graphs register in `langgraph dev`. Cheap offline checks first; live end-to-end runs are reserved for TG milestones since they spend API credit.

### TG 01.3: OpenRouter Integration

Add OpenRouter as a second LLM provider alongside OpenAI. OpenRouter uses the OpenAI-compatible API format, so `langchain-openai` works with a different base URL and API key. The selection is controlled by a `LLM_PROVIDER` env var.

Model mapping (OpenAI → OpenRouter equivalents, post-rebalancing):

| Tier | OpenAI          | OpenRouter                        |
| ---- | --------------- | --------------------------------- |
| low  | gpt-4o-mini     | google/gemma-4-26b-a4b-it         |
| mid  | gpt-4.1-mini    | anthropic/claude-haiku-4.5        |
| high | gpt-4.1         | anthropic/claude-sonnet-5         |

**Important:** The voting mechanism (3 completions, 2/3 consensus) and evidence evaluation must use capable models. Do not map the evidence evaluation call below the high tier (gpt-4.1 / Sonnet 5). Sonnet 5 reasoning effort is set to "medium" via `REASONING_CONFIG`.

**Prep findings (Session 2):**
- The single integration point is `utils/models.py:get_llm()` — it hardwires `settings.openai_api_key`. The only explicit model override in the codebase is `claim_verifier/nodes/evaluate_evidence.py:92` (`openai:gpt-4.1`).
- The `MODEL_NAME` constants in both `llm/config.py` files are **dead code** — never passed to `get_llm()`. At runtime everything uses gpt-4o-mini except evidence evaluation. The mapping table above describes intent, not current behavior; TG 01.3 wires per-role model config for real.
- The `sk-proj-` prefix validator on `openai_api_key` in `utils/settings.py` will reject OpenRouter keys — OpenRouter gets its own settings field.
- **TDD:** this TG introduces the repo's first tests (`tests/`, pytest). Provider selection and settings validation are unit-testable offline; live API runs only at the TG milestone.

### TG 01.4: PDF Ingest

Add a thin `ingest/` module that reads PDFs and outputs structured text. Reuse the Docling process from doc-rag-backend where possible — it already handles PDF parsing with sentence-level output.

**Investigation needed (on Mac):** Check doc-rag-backend for a standalone function that takes a PDF and returns sentences with metadata. If it exists, extract or import it.

**Decision (user, Session 2):** Use `docling` directly, without waiting on the doc-rag-backend investigation. The transitive ML deps (torch etc.) are accepted — they are used dependencies of a real feature, unlike the removed declared-but-unused ones. Align output formats with doc-rag-backend later if the Mac investigation surfaces a better pattern.

The ingest module feeds sections to the existing fact-checker graph. Long papers are chunked by section and processed independently.

### TG 01.5: Claimify Skill

Create `.claude/skills/claimify.md` that orchestrates the full pipeline from Claude Code:

1. Start LangGraph dev server (if not running)
2. Accept a file path argument (PDF or text)
3. Extract text via ingest module
4. Run fact-checker per section
5. Write results to `workspace/output/`

### TG 01.6: Quality & Wrap

End-to-end test on a real paper. Update handover.

## Success Criteria

- `langgraph dev` starts from the flattened repo root
- A PDF dropped in `workspace/inbox/` can be fact-checked via `/claimify`
- Both OpenAI and OpenRouter providers work
- Results are written as structured JSON + readable Markdown report

---

## Phase 02 Preview: Vault Verification Core

**Planned — see `phase-02-vault-verification-core.md`.** Session 4 design discussion replaced the original "Argument Chain Verification" concept: Phase 02 now verifies a markdown draft (wikilink citations) against its trusted Obsidian vault — cited-claim alignment plus batch vault matching for citation-free claims — with routing/corpus (03), deep-research commissions (04), and the draft update loop (05) as follow-on phases. Chain-completeness checking of the vault itself moved to the edge-case backlog.

## Lessons

### Session 2 (2026-07-22)

1. **NLTK blocks the ASGI event loop.** The sentence tokenizer (punkt) makes a synchronous socket call on first use. `langgraph dev` must run with `--allow-blocking`, and punkt data must be pre-downloaded. Fixed in `scripts/dev.py` — the `poetry run dev` script handles both.

2. **Windows MAX_PATH breaks torch installs.** Poetry's default venv path (`~\AppData\Local\pypoetry\Cache\virtualenvs\...`) exceeds 260 chars when torch unpacks nested third-party licenses. Fix: `poetry config virtualenvs.path C:\vpy --local` (gitignored `poetry.toml`). Permanent fix: enable long paths in registry (`LongPathsEnabled=1`, needs admin).

3. **Docling model downloads can wedge.** First-run HuggingFace model download (~505 MB) hung on a half-open CDN connection. Recovery: kill the process, retry with `HF_HUB_OFFLINE=1` against the populated cache. Once cached, extraction runs in ~16s.

4. **Model tier abstraction is worth doing early.** The original role-based registry (5 roles × 2 providers) was confusing — multiple roles mapped to the same model, making cross-provider comparison hard. Refactoring to 3 tiers (low/mid/high) simplified the registry, made costs comparable at a glance, and let the user immediately spot that the OpenRouter tiers were over-specced. Record rationale in a playbook doc, not just code comments.

5. **Prep import/path analysis saved significant time.** The flatten (TG 01.2, 199 files changed) completed with zero import rewrites because prep confirmed all imports were absolute top-level package names with no sys.path hacks. Without that confidence the flatten would have required iterative testing after each batch of moves.

### Session 3 (2026-07-23)

6. **Check installed library capabilities before designing workarounds.** Prep discovered that `ChatOpenAI` in langchain-openai already has a built-in `reasoning_effort` parameter — no `extra_body` hack needed. Grepping the installed package source (`langchain_openai/chat_models/base.py`) revealed the parameter at line 504, saving a custom implementation.

7. **Cost tracking needs to be purpose-built.** The only existing token-related code (`estimate_token_count` in `utils/llm.py`) is for truncation, not tracking. No infrastructure exists for API usage monitoring — it must be built from scratch for search providers.

8. **Architecture audit at phase boundary found clean structure.** Dependency direction is correct across all packages (all imports point inward). Zero config duplication, zero model name hardcoding outside the registry. One dead-code finding: `utils/__init__.py` exports 3 checkpointer functions that don't exist — cleanup task added.

9. **Simple call-counter over class-based tracker for cost tracking.** Langchain's Exa/Tavily wrappers don't expose response metadata (usage stats, remaining credits). Cost tracking must be call-count-based with hardcoded per-call estimates. Phase 02 (argument chain verification) doesn't use web search, so this is Phase 01-specific — a class-based `CostTracker` with generic operation types would be YAGNI.

10. **Separate secrets from config immediately.** `.env` for API keys, `config.toml` for everything else (provider, models, search settings). This paid off within the same session — switching providers for live tests became a one-line edit to a non-sensitive, committed file instead of touching the secrets file. Python 3.11 has `tomllib` built in.

11. **First full academic paper costs $10 with default settings.** The ukraine working paper (7,000 words, 20 sections) produced 448 claims — far more than estimated — each getting up to 5 search iterations and a GPT-4.1 evaluation call. GPT-4.1 (high tier) was 76% of total cost ($7.70 of $10.07) despite only 6% of requests (448 of 7,209). Three optimization routes identified: (a) evidence summarization by a cheaper model before high-tier evaluation, (b) triage-based routing so trivial claims get less effort, (c) claim-type routing so novel results go to vault verification not web search. The $10/paper baseline is what Phases 02–03 need to beat. Full breakdown in `memory/project_phase01_cost_analysis.md`.

12. **LangGraph dev server processes can be hard to kill on Windows.** The server spawns child processes that persist after the parent is killed. `netstat -ano | findstr ":PORT"` shows the PIDs but they can resist `Stop-Process`. Workaround: start new servers on different ports (2025, 2026) rather than fighting zombie processes.
