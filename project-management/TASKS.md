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
- [x] 01.3.3 Dead `MODEL_NAME` constants retired; `MODEL_REGISTRY` (tier × provider) is now the single source of truth; nodes pass tiers (low/mid/high). Refactored from 5 roles to 3 tiers per user request for simpler abstraction.
- [x] 01.3.4 `evaluate_evidence.py` routed through `high` tier. OpenRouter mapping rebalanced per user review: low=gemma-4-26b-a4b-it, mid=haiku-4.5, high=sonnet-5 (Opus dropped as over-specced). Model selection playbook at `docs/playbook/model-tier-selection.md`.
- [x] 01.3.5a OpenAI provider live-tested: Apollo 11 paragraph → 14 claims extracted, 12 supported, 2 refuted. Pipeline end-to-end verified.
- [x] 01.3.5b OpenRouter provider live test — passed (Session 3): 2 claims, 2 supported. Full Gemma 4 → Haiku 4.5 → Sonnet 5 (reasoning_effort=medium) chain via Exa search.
- [x] 01.3.6 Docs: `docs/llm-providers.md` mapping table, CLAUDE.md, `.env.example`, INSTALLATION.md, LLM cost section in websearch-and-costs.md (OpenRouter pricing verified; OpenAI list prices flagged as needing confirmation)
- [x] 01.3.7a Write tests for reasoning effort parameter on high-tier OpenRouter models (`tests/test_models.py`) → NARROW (5 tests added)
- [x] 01.3.7b Implement reasoning effort in `_get_openrouter_llm()` — `ChatOpenAI(reasoning_effort=...)` built-in parameter; `REASONING_CONFIG` dict alongside `MODEL_REGISTRY`; high tier gets "medium", low/mid get None

Session 3 note: Prep discovered that `ChatOpenAI` in langchain-openai already has a built-in `reasoning_effort` parameter (str: "low"/"medium"/"high"). No `extra_body` hack needed. The parameter is passed directly in the Chat Completions request body, which OpenRouter's OpenAI-compatible endpoint should accept.

### TG 01.4: PDF Ingest

TDD: fixture PDF in `tests/fixtures/`; extraction and chunking are unit-testable offline.

- [x] 01.4.1 doc-rag-backend investigation superseded — user decided (2026-07-22): use Docling directly; align formats with doc-rag-backend later if the Mac investigation warrants it
- [x] 01.4.2 Integration approach: direct docling library use, confined to `ingest/pdf.py` (lazy import)
- [x] 01.4.3a/b `ingest/` implemented TDD: extract_pdf → markdown; 24 tests in `tests/test_ingest.py`
- [x] 01.4.4a/b Chunking implemented TDD: heading split (H1/H2, code-fence aware), 4000-char cap on paragraph boundaries, <200-char section merging
- [x] 01.4.5 `workspace/inbox/` + `workspace/output/` with .gitkeep; contents gitignored; workspace/README.md
- [x] 01.4.6 `scripts/run_from_pdf.py` — argparse CLI, per-section runs.wait against fact_checker, results.json + report.md output, clear server-not-running error. Live invocation untested (no server/keys)
- [x] 01.4.7 Test on a real academic paper → FULL — PASSED (Session 4): ukraine working paper PDF (7,000 words) → 20 sections extracted via Docling, 448 claims verified via OpenAI+Exa. Cost: ~$10 (see Lesson 11 in phase plan). Verdicts: factual/historical claims verify well; novel results correctly get "refuted" (web has no source). Output: `workspace/output/MS-DRAFT-working-paper-v4/`

Session 2 note: docling first-run model download (~505 MB) hung once on a wedged HF CDN connection; killed and re-ran with HF_HUB_OFFLINE=1 against the populated cache (~40s). Models now cached; future runs need no download.

### TG 01.5: Claimify Skill

- [x] 01.5.1 Skill created at `.claude/skills/claimify/SKILL.md` (directory+SKILL.md is the current Claude Code convention, supersedes the planned flat claimify.md path) — covers input resolution, .env preflight, server start, run command, cost warning, results presentation, failure modes
- [x] 01.5.2 Output format defined: `workspace/output/<stem>/results.json` + `report.md` (implemented in TG 01.4, documented in skill). `run_from_pdf.py` extended to accept .md/.txt/.markdown input (8 new offline tests; 31 total in test_ingest.py)
- [ ] 01.5.3 Test end-to-end: `/claimify workspace/inbox/paper.pdf` → NOT YET TESTED. Session 4 ran `run_from_pdf.py` directly (which passed); the `/claimify` skill wrapper was not exercised.

### TG 01.6: Quality & Wrap — IN PROGRESS

- [x] 01.6.1a OpenAI provider live test passed (Apollo 11 paragraph, 14 claims, 12/2 supported/refuted)
- [x] 01.6.1b OpenRouter provider live test — passed (Session 3): Apollo 11 input → 2 claims, 2 supported. All 3 tiers exercised (Gemma 4 / Haiku 4.5 / Sonnet 5 with reasoning_effort=medium) via Exa.
- [x] 01.6.1c Exa vs Tavily comparison — passed (Session 3): same input, Exa → 2 claims/2 supported (30KB output), Tavily → 3 claims/3 supported (1.1MB output). Tavily returns much more raw content; both produce correct verdicts.
- [x] 01.6.1d Real academic paper PDF test — PASSED (Session 4): ukraine working paper, OpenAI+Exa, 448 claims across 20 sections. Option 1 scope ("does the pipeline run?") — yes. Web verdicts on novel results are correctly shallow. Cost analysis recorded as Lesson 11. Design discussion for academic verification scope completed → Phase 02 plan written.
- [x] 01.6.1e-a Write tests for search cost counter (`tests/test_cost_tracking.py`): 12 tests covering counting, cost calculation, free-tier balance, reset, print_summary
- [x] 01.6.1e-b Implement simple call counter in `utils/cost_tracking.py`: process-local counters with INFO logging per search call; `print_summary()` for direct invocation; cross-process limitation documented
- [x] 01.6.1e-c Add `record_search()` calls in `claim_verifier/nodes/retrieve_evidence.py` after Exa/Tavily searches succeed

Session 3 system-thinking decision: Use simple call-counter approach (not a CostTracker class). Langchain search wrappers don't expose response metadata (usage/credit info), so tracking is call-count-based with hardcoded cost estimates. Phase 02 (argument chain verification) doesn't use web search, so this module is Phase 01-specific — no need for generic operation tracking.

Session 3 completion review fix: Counters are process-local — `record_search()` in the LangGraph server process can't be read by `print_summary()` in the client process (`run_from_pdf.py`). Fix: removed misleading client-side calls; added INFO-level logging per search call so costs appear in the server's terminal output. `print_summary()` is kept for direct (in-process) invocation only.
- [x] 01.6.2 Update HANDOVER.md
- [x] 01.6.3 Push to origin — confirmed pushed (Session 2 end)

Fixes (Session 4):
- [x] 01.6.6 Fix `scripts/dev.py` emoji encoding issue — removed all 8 emoji characters from print statements; `poetry run dev` no longer crashes with UnicodeEncodeError on Windows cp1252. (`scripts/api_key.py` has the same issue but is dormant Redis auth code — not urgent.)

Cleanup (from Session 3 architecture audit):
- [x] 01.6.4 Remove dead checkpointer exports from `utils/__init__.py` (`create_checkpointer`, `setup_checkpointer`, `create_checkpointer_sync` removed from `__all__`)

Unplanned (Session 3, user-requested):
- [x] 01.6.5 Extract non-sensitive config from `.env` to `config.toml` — `utils/config.py` loads TOML; `MODEL_REGISTRY`, `REASONING_CONFIG`, `llm_provider`, `search_provider`, `results_per_query`, `max_search_iterations` all read from config.toml with hardcoded fallbacks. Env vars still override via Pydantic. 7 new tests in `tests/test_config.py`. `LLM_PROVIDER` removed from `.env` and `.env.example`.

Acceptance criteria for TG 01.6:
- OpenRouter live test produces at least 1 supported or refuted claim on short input
- Exa and Tavily both return evidence for the same input (quality comparison is informational)
- Cost counter reports search count and estimated cost after a live run
- Real academic paper produces structured JSON + markdown report via run_from_pdf

---

## Phase 02: Vault Verification Core — PLANNED

Plan: `phase-plans/phase-02-vault-verification-core.md` (supersedes the old "Argument Chain Verification" Phase 02 — chain-completeness checking moved to the edge-case backlog; design decisions from Session 4 recorded in the plan's Design pillars).

Best case first: markdown draft with wikilink citations + trusted vault. Test corpus: `../ukraine-vote-analysis` working paper.

### TG 02.1: Claim Record, Run Profiles, Resource Manifest

- [ ] 02.1.1 Claim record Pydantic models (citation status, cite set, position, per-route verdicts + provenance, suggested action; Phase 03 placeholder fields)
- [ ] 02.1.2 Resource manifest model + loader (vault-less manifest validates and degrades, not errors)
- [ ] 02.1.3 Run profiles: light (= Phase 01 behavior, regression-tested) / heavy
- [ ] 02.1.4 Design doc in `docs/playbook/` — attribute taxonomies and which phase populates each

### TG 02.2: Draft Ingestion and Citation Binding

- [ ] 02.2.1 Parse wikilinked markdown draft → claims with section + position offsets
- [ ] 02.2.2 Cite-set binding (union semantics; multi-cite sentences; trailing-cite scope heuristic documented + tested)
- [ ] 02.2.3 Citation markers survive Claimify decomposition (bind before/alongside; tested)
- [ ] 02.2.4 Non-wikilink citations flagged `unparsed-citation`, not bound

### TG 02.3: Vault Serializer

- [ ] 02.3.1 Vault → JSON (name, type, frontmatter, key sections, wikilinks); read-only
- [ ] 02.3.2 Filtering by `argument_pyramid` and note type; token accounting with budget warning
- [ ] 02.3.3 Graceful degradation on schema drift; validated against real ukraine vault (421 notes)

### TG 02.4: Cited-Claim Alignment

- [ ] 02.4.1 Resolve cite set → SOURCE → QUOTE/PARA notes; evaluate support at `high` tier
- [ ] 02.4.2 Verdicts: supported (provenance) / not-supported (miscite) / source-not-in-vault / insufficient-vault-content
- [ ] 02.4.3 Live spot-check on real draft claims

### TG 02.5: Citation-Free Vault Matching

- [ ] 02.5.1 Batch match: one call, all claims + serialized vault → candidate matches (cost scales with vault size)
- [ ] 02.5.2 Verify pass per match at `high` tier: vault-supported / vault-contradicted / no-vault-match
- [ ] 02.5.3 Copy `claim_strength`/`evidence_quality` from matched vault CLAIM notes; `no-vault-match` handed off clean for Phase 03

### TG 02.6: Gap Report v2

- [ ] 02.6.1 results.json (full claim records) + report.md with per-claim verdicts, provenance, suggested actions
- [ ] 02.6.2 Manifest-adaptive sections; explicit vault-improvement signals
- [ ] 02.6.3 Light-profile report stays Phase 01-compatible

### TG 02.7: Quality & Wrap

- [ ] 02.7.1 MILESTONE: heavy run over ukraine working paper → gap report judged useful by user
- [ ] 02.7.2 Light-run regression on non-vault document
- [ ] 02.7.3 docs-align-check, docs/HANDOVER/TASKS updated, pushed to origin

---

## Phases 03–05: Roadmap — FUTURE

- **Phase 03 — Routing & Corpus:** triage classifier, web route reuse, doc-rag-backend client (api.ragtogo.com, `document_ids` scoping), routing policy for no-vault-match claims
- **Phase 04 — Deep Research Commissions:** human-approved escalation, commission writer, response-paper ingestion + re-evaluation
- **Phase 05 — Draft Update Loop:** propose citation-inserting draft edits after vault improvement

**Edge-case backlog:** PDF-only drafts / plain-text citation parsing; source fetching for absent papers; vault-less heavy runs; vault QA / chain completeness (old Phase 02 concept); semi-automated vault enrichment
