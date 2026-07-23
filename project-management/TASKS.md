# Task List

## Numbering Convention

| Level      | Format     | Example  |
| ---------- | ---------- | -------- |
| Phase      | `Phase ##` | Phase 01 |
| Task Group | `TG ##.#`  | TG 01.1  |
| Task       | `##.#.#`   | 01.1.1   |

## Status Key

- **[x]** - Completed
- **[ ]** - Outstanding

---

## Phase 01: Foundation & Core Pipeline — IN PROGRESS

### TG 01.1: PM Structure — COMPLETE

- [x] 01.1.1 Create CLAUDE.md with project overview, pipeline docs, conventions
- [x] 01.1.2 Create HANDOVER.md
- [x] 01.1.3 Create project-management/ with TASKS.md and phase plan
- [x] 01.1.4 Create REPO note in control hub vault
- [x] 01.1.5 Update control hub master index

### TG 01.2: Strip to Agent-Only — COMPLETE

Structural work — no new logic, so no TDD; verified by import/graph-load smoke checks.

- [x] 01.2.1 Relocate a slimmed `docker-compose.yml` (Redis + Postgres 17) from `apps/web/docker-compose.yml` to repo root
- [x] 01.2.2 Move `apps/agent/*` contents to repo root (58 renames, no import rewrites needed)
- [x] 01.2.3 Remove `apps/web/`, `apps/extension/`, `apps/` directory
- [x] 01.2.4 Remove root `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `turbo.json`
- [x] 01.2.5 Remove `.github/workflows/deploy.yml` (whole `.github/` dir — it was the only file)
- [x] 01.2.6 Remove `Dockerfile` and `fly.toml`
- [x] 01.2.7 Remove unused deps: torch, transformers, sentence-transformers, huggingface-hub, scikit-learn, scipy, numpy (nltk kept); `poetry lock` + `poetry install` clean
- [x] 01.2.8 pyproject cleanup: `security` added to packages; dangling `create-run` script entry removed
- [x] 01.2.9 Agent README promoted to root with fork framing; INSTALLATION.md rewritten agent-only (incl. REDIS_URI+REDIS_URL gotcha); utils/README.md wording fixed
- [x] 01.2.10 Verified: all three packages import; `langgraph dev` registers all 3 graphs at 127.0.0.1:2024
- [x] 01.2.11 CLAUDE.md directory layout verified — already matched post-flatten reality, no changes needed

Session 2 environment notes: Poetry 2.4.1 installed via `uv tool install poetry`, pointed at uv-managed Python 3.11.15 (PATH python.exe is the Windows Store stub). langgraph-cli pinned at 0.4.8 / langgraph-api 0.4.48 in the venv to match langgraph 0.4.x pins (EOL warning is cosmetic).

### TG 01.3: OpenRouter Integration

TDD: new `tests/` directory (pytest). Provider selection is unit-testable without API calls.
Tiers: NARROW = targeted test file, no network. MID = full pytest suite. FULL = live end-to-end (spends API credit — milestones only).

- [ ] 01.3.1a Set up pytest; write failing tests for settings (`LLM_PROVIDER` values, `OPENROUTER_API_KEY` field, existing `sk-proj-` validator untouched) in `tests/test_settings.py` → NARROW
- [ ] 01.3.1b Implement `LLM_PROVIDER` + `OPENROUTER_API_KEY` in `utils/settings.py` (tests pass) — OpenRouter key MUST be its own field: the `sk-proj-` validator rejects OpenRouter keys → NARROW
- [ ] 01.3.2a Write failing tests for `get_llm()` provider branching (openai default unchanged; openrouter → base_url + openrouter key) in `tests/test_models.py` → NARROW
- [ ] 01.3.2b Implement OpenRouter branch in `utils/models.py:get_llm()` (tests pass) → NARROW
- [ ] 01.3.3 Reconcile dead `MODEL_NAME` constants: `llm/config.py` values are never passed to `get_llm()` — wire per-role model selection (incl. provider-specific mapping) through config so the mapping table is real, not aspirational → MID
- [ ] 01.3.4 Route `claim_verifier/nodes/evaluate_evidence.py:92` hardcoded model through the mapping (Opus-tier on OpenRouter — never below) → MID
- [ ] 01.3.5 Live test both providers with a 1–2 claim input → FULL
- [ ] 01.3.6 Docs: model mapping table, CLAUDE.md env vars, `.env.example` (`OPENROUTER_API_KEY`, `LLM_PROVIDER`), add LLM cost section to `docs/websearch-and-costs.md`

### TG 01.4: PDF Ingest

TDD: fixture PDF in `tests/fixtures/`; extraction and chunking are unit-testable offline.

- [ ] 01.4.1 Investigate doc-rag-backend Docling process on Mac (BLOCKED on Windows — fallback: use `docling` or `pymupdf` directly; don't stall the TG on this)
- [ ] 01.4.2 Determine integration approach: import as dependency, extract as standalone module, or direct library use
- [ ] 01.4.3a Write failing tests for `ingest/` (PDF → sections with text + metadata) in `tests/test_ingest.py` → NARROW
- [ ] 01.4.3b Implement `ingest/` module (tests pass) → NARROW
- [ ] 01.4.4a Write failing tests for section chunking (long text → fact-checker-sized sections) → NARROW
- [ ] 01.4.4b Implement chunking (tests pass) → NARROW
- [ ] 01.4.5 Create `workspace/inbox/` and `workspace/output/` directories
- [ ] 01.4.6 Write `scripts/run_from_pdf.py` — PDF path → extract → fact-check per section → write results → MID
- [ ] 01.4.7 Test on a real academic paper → FULL

### TG 01.5: Claimify Skill

- [ ] 01.5.1 Create `.claude/skills/claimify.md` — orchestrates: start LangGraph server, accept file path, extract text, run fact-checker, write results
- [ ] 01.5.2 Define output format (JSON + Markdown report in workspace/output/)
- [ ] 01.5.3 Test end-to-end: `/claimify workspace/inbox/paper.pdf`

### TG 01.6: Quality & Wrap

- [ ] 01.6.1 Verify full pipeline works end-to-end (PDF → claims → verdicts → report) → FULL (one clean run on a real paper is the milestone gate; use a short 1–2 claim input for any debugging iterations to protect API quota)
- [ ] 01.6.2 Update HANDOVER.md
- [ ] 01.6.3 Commit and push to origin

---

## Phase 02: Argument Chain Verification — FUTURE

### TG 02.1: Vault Integration (design)

- [ ] 02.1.1 Design how ClaimeAI reads argument pyramid notes from an Obsidian vault
- [ ] 02.1.2 Define what "present" and "missing" means for argument chain links
- [ ] 02.1.3 Design gap report output format

### TG 02.2: Chain Verification Workflow

- [ ] 02.2.1 Build vault reader that maps argument pyramid structure (CLAIM, QUOTE, PARA, OBS, THESIS, HYP, REC notes)
- [ ] 02.2.2 Implement chain completeness checker — walk the pyramid, identify missing links
- [ ] 02.2.3 Generate gap report with actionable items

### TG 02.3: Gap Action Workflow (advanced)

- [ ] 02.3.1 Present gaps interactively — user indicates what to do about each
- [ ] 02.3.2 Execute gap-filling actions (search for evidence, draft missing claims, etc.)
