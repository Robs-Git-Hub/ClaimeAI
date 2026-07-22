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

### TG 01.2: Strip to Agent-Only

- [ ] 01.2.1 Move `apps/agent/*` contents to repo root
- [ ] 01.2.2 Remove `apps/web/`, `apps/extension/`, `apps/` directory
- [ ] 01.2.3 Remove root `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `turbo.json`
- [ ] 01.2.4 Remove `.github/workflows/deploy.yml` (Fly.io CI, currently disabled)
- [ ] 01.2.5 Remove `Dockerfile` and `fly.toml` (cloud deploy config — not needed for local use)
- [ ] 01.2.6 Remove unused ML dependencies from pyproject.toml: torch, transformers, sentence-transformers, huggingface-hub, scikit-learn, scipy
- [ ] 01.2.7 Update langgraph.json paths if needed after flatten
- [ ] 01.2.8 Verify `langgraph dev` starts and `scripts/run_fact_checker.py` runs
- [ ] 01.2.9 Update CLAUDE.md directory layout section

### TG 01.3: OpenRouter Integration

- [ ] 01.3.1 Add `langchain-openai` OpenRouter-compatible configuration to `utils/models.py`
- [ ] 01.3.2 Add `LLM_PROVIDER` env var (values: `openai`, `openrouter`) to `utils/settings.py`
- [ ] 01.3.3 Add `OPENROUTER_API_KEY` to settings with appropriate validation
- [ ] 01.3.4 Update `claim_extractor/llm/config.py` to select provider based on setting
- [ ] 01.3.5 Update `claim_verifier/llm/config.py` to select provider based on setting
- [ ] 01.3.6 Update hardcoded model in `claim_verifier/nodes/evaluate_evidence.py`
- [ ] 01.3.7 Add model mapping table (OpenAI model → OpenRouter equivalent) to docs
- [ ] 01.3.8 Test with OpenRouter API key and Claude models via OpenRouter
- [ ] 01.3.9 Update CLAUDE.md env vars section and docs

### TG 01.4: PDF Ingest

- [ ] 01.4.1 Investigate doc-rag-backend Docling process on Mac — identify function that outputs sentences/spans from PDF
- [ ] 01.4.2 Determine integration approach: import as dependency, extract as standalone module, or call via API
- [ ] 01.4.3 Create `ingest/` module with PDF → text extraction
- [ ] 01.4.4 Add section chunking — split extracted text into sections suitable for fact-checker input
- [ ] 01.4.5 Create `workspace/inbox/` and `workspace/output/` directories
- [ ] 01.4.6 Write `scripts/run_from_pdf.py` — takes PDF path, extracts text, runs fact-checker per section, writes results
- [ ] 01.4.7 Test on a real academic paper

### TG 01.5: Claimify Skill

- [ ] 01.5.1 Create `.claude/skills/claimify.md` — orchestrates: start LangGraph server, accept file path, extract text, run fact-checker, write results
- [ ] 01.5.2 Define output format (JSON + Markdown report in workspace/output/)
- [ ] 01.5.3 Test end-to-end: `/claimify workspace/inbox/paper.pdf`

### TG 01.6: Quality & Wrap

- [ ] 01.6.1 Verify full pipeline works end-to-end (PDF → claims → verdicts → report)
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
