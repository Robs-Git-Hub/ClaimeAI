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

- [x] 01.3.1a Failing tests for settings written first (13 tests, env-isolated)
- [x] 01.3.1b `LLM_PROVIDER` (case-insensitive, validated) + `OPENROUTER_API_KEY` (`sk-or-` prefix) in `utils/settings.py`
- [x] 01.3.2a Failing tests for `get_llm()` provider branching written first (19 tests, no network)
- [x] 01.3.2b OpenRouter branch in `utils/models.py` (ChatOpenAI vs openrouter.ai/api/v1; temperature honored both paths incl. voting 0.2 rule)
- [x] 01.3.3 Dead `MODEL_NAME` constants retired; `MODEL_REGISTRY` (role × provider) is now the single source of truth; nodes pass roles. Note: query_generation/search_decision now genuinely run gpt-4.1-mini on openai (previously silently ran the gpt-4o-mini default) — matches documented intent, pre-approved
- [x] 01.3.4 `evaluate_evidence.py` routed through `evidence_evaluation` role; Opus-tier floor commented in registry. OpenRouter IDs verified live 2026-07-22: claude-haiku-4.5 / claude-sonnet-5 / claude-opus-4.8
- [ ] 01.3.5 Live test both providers with a 1–2 claim input → FULL — BLOCKED: needs OPENROUTER_API_KEY + OPENAI_API_KEY in .env (no keys in this environment); re-confirm OpenRouter model IDs at first paid run
- [x] 01.3.6 Docs: `docs/llm-providers.md` mapping table, CLAUDE.md, `.env.example`, INSTALLATION.md, LLM cost section in websearch-and-costs.md (OpenRouter pricing verified; OpenAI list prices flagged as needing confirmation)

### TG 01.4: PDF Ingest

TDD: fixture PDF in `tests/fixtures/`; extraction and chunking are unit-testable offline.

- [x] 01.4.1 doc-rag-backend investigation superseded — user decided (2026-07-22): use Docling directly; align formats with doc-rag-backend later if the Mac investigation warrants it
- [x] 01.4.2 Integration approach: direct docling library use, confined to `ingest/pdf.py` (lazy import)
- [x] 01.4.3a/b `ingest/` implemented TDD: extract_pdf → markdown; 24 tests in `tests/test_ingest.py`
- [x] 01.4.4a/b Chunking implemented TDD: heading split (H1/H2, code-fence aware), 4000-char cap on paragraph boundaries, <200-char section merging
- [x] 01.4.5 `workspace/inbox/` + `workspace/output/` with .gitkeep; contents gitignored; workspace/README.md
- [x] 01.4.6 `scripts/run_from_pdf.py` — argparse CLI, per-section runs.wait against fact_checker, results.json + report.md output, clear server-not-running error. Live invocation untested (no server/keys)
- [ ] 01.4.7 Test on a real academic paper → FULL — BLOCKED on API keys (same gate as 01.3.5 / TG 01.6)

Session 2 note: docling first-run model download (~505 MB) hung once on a wedged HF CDN connection; killed and re-ran with HF_HUB_OFFLINE=1 against the populated cache (~40s). Models now cached; future runs need no download.

### TG 01.5: Claimify Skill

- [x] 01.5.1 Skill created at `.claude/skills/claimify/SKILL.md` (directory+SKILL.md is the current Claude Code convention, supersedes the planned flat claimify.md path) — covers input resolution, .env preflight, server start, run command, cost warning, results presentation, failure modes
- [x] 01.5.2 Output format defined: `workspace/output/<stem>/results.json` + `report.md` (implemented in TG 01.4, documented in skill). `run_from_pdf.py` extended to accept .md/.txt/.markdown input (8 new offline tests; 31 total in test_ingest.py)
- [ ] 01.5.3 Test end-to-end: `/claimify workspace/inbox/paper.pdf` → FULL — BLOCKED on API keys (same gate as 01.3.5/01.4.7/01.6.1)

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
