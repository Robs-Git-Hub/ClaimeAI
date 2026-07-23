# Phase 01: Foundation & Core Pipeline

**Status:** IN PROGRESS
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

Model mapping (OpenAI → OpenRouter/Claude equivalents):

| Current (OpenAI)  | Role                      | OpenRouter equivalent    |
| ------------------ | ------------------------- | ------------------------ |
| gpt-4o-mini        | Claim extraction (all)    | claude-haiku-4-5         |
| gpt-4.1-mini       | Query gen, search decision| claude-sonnet-4           |
| gpt-4.1            | Evidence evaluation       | claude-opus-4             |

**Important:** The voting mechanism (3 completions, 2/3 consensus) and evidence evaluation must use capable models. Do not map the evidence evaluation call to anything below Opus-tier.

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

## Phase 02 Preview: Argument Chain Verification

**Not started.** Future phase that integrates ClaimeAI with Obsidian vaults containing argument pyramids (from the article-writer-research-of-agents pipeline). Instead of verifying claims against the web, this workflow checks for present and missing links in argument chains and outputs a gap report. An advanced version lets the user indicate what to do about each gap.

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
