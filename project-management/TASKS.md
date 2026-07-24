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

## Phase 01: Foundation & Core Pipeline — COMPLETE (Session 5)

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
- [x] 01.4.6 `scripts/run_from_pdf.py` — argparse CLI, per-section runs.wait against fact_checker, results.json + report.md output, clear server-not-running error. Live invocation verified in 01.4.7 (Session 4).
- [x] 01.4.7 Test on a real academic paper → FULL — PASSED (Session 4): ukraine working paper PDF (7,000 words) → 20 sections extracted via Docling, 448 claims verified via OpenAI+Exa. Cost: ~$10 (see Lesson 11 in phase plan). Verdicts: factual/historical claims verify well; novel results correctly get "refuted" (web has no source). Output: `workspace/output/MS-DRAFT-working-paper-v4/`

Session 2 note: docling first-run model download (~505 MB) hung once on a wedged HF CDN connection; killed and re-ran with HF_HUB_OFFLINE=1 against the populated cache (~40s). Models now cached; future runs need no download.

### TG 01.5: Claimify Skill — COMPLETE

- [x] 01.5.1 Skill created at `.claude/skills/claimify/SKILL.md` (directory+SKILL.md is the current Claude Code convention, supersedes the planned flat claimify.md path) — covers input resolution, .env preflight, server start, run command, cost warning, results presentation, failure modes
- [x] 01.5.2 Output format defined: `workspace/output/<stem>/results.json` + `report.md` (implemented in TG 01.4, documented in skill). `run_from_pdf.py` extended to accept .md/.txt/.markdown input (8 new offline tests; 31 total in test_ingest.py)
- [x] 01.5.3 Test end-to-end — PASSED (Session 5): `/claimify workspace/inbox/ukraine-intro-test.txt` (2 intro paragraphs of the ukraine paper). Skill wrapper exercised fully: preflight, server start, run, results presentation, and the failure path (first attempt hit OpenAI 429 insufficient_quota — error recorded cleanly in results.json/report.md, not silently dropped). Re-run via `LLM_PROVIDER=openrouter` env override: 15 claims, 10 supported, 5 refuted. Note: OpenAI account is out of API credit as of Session 5.

### TG 01.6: Quality & Wrap — COMPLETE

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

## Phase 02: Vault Verification Core — COMPLETE (Session 8)

Plan: `phase-plans/phase-02-vault-verification-core.md` (supersedes the old "Argument Chain Verification" Phase 02 — chain-completeness checking moved to the edge-case backlog; design decisions from Session 4 recorded in the plan's Design pillars).

Best case first: markdown draft with wikilink citations + trusted vault. Test corpus: `../ukraine-vote-analysis` working paper.

### TG 02.1: Claim Record, Run Profiles, Resource Manifest

Design doc first (the Phase 03–05 contract), then TDD for all models. No pipeline code changes — models only.
New files: `utils/claim_record.py`, `utils/run_config.py`, `tests/test_claim_record.py`, `tests/test_run_config.py`.

- [x] 02.1.1 Design doc: `docs/playbook/claim-record-design.md` — attribute taxonomy (citation status, verdict routes, suggested actions, Phase 03 placeholders), which phase populates each field, verdict types per route
- [x] 02.1.2a Write tests for claim record models (`tests/test_claim_record.py`): DraftPosition, CitationStatus enum, RouteVerdict, ClaimRecord construction, Phase 03 placeholder fields default to None, round-trip serialization → NARROW (23 tests)
- [x] 02.1.2b Implement claim record Pydantic models in `utils/claim_record.py`: ClaimRecord wraps Verdict (not replaces), adds citation_status, cite_set, draft position, per-route verdicts with provenance, suggested_action; VaultVerdict enum separate from existing VerificationResult → NARROW (23 pass)
- [x] 02.1.3a Write tests for resource manifest + run profile (`tests/test_run_config.py`): manifest validation (valid with vault, valid without vault, invalid paths), loader from dict/kwargs, RunProfile enum, profile defaults → NARROW (20 tests)
- [x] 02.1.3b Implement resource manifest + run profile in `utils/run_config.py`: ResourceManifest (draft_path, optional vault_path, optional corpus_ids, web_enabled flag), RunProfile enum (light/heavy), manifest without vault validates and degrades → NARROW (20 pass)
- [x] 02.1.4 TG 02.1 complete — regression check: 130 passed, 1 deselected (slow) → MID (`pytest -m "not slow"`)

### TG 02.2: Draft Ingestion and Citation Binding

Architecture: pre-process draft to extract citations + strip wikilinks → send clean text through unchanged Phase 01 pipeline → re-attach citations to output claims via `original_index`. No pipeline code changes.
New files: `ingest/draft_types.py` (shared types), `ingest/draft_parser.py` (parsing), `ingest/citation_binder.py` (binding), `tests/test_draft_parser.py`, `tests/test_citation_binder.py`.
Trailing citation scope heuristic: sentence-level only (conservative — a wrong "citation-free" beats a wrong binding).

- [x] 02.2.0 Shared data types in `ingest/draft_types.py`: WikilinkCitation, ParsedSentence, ParsedDraft
- [x] 02.2.1a Write tests for draft parser (`tests/test_draft_parser.py`): wikilink regex, strip, sentence splitting, author-year detection, ParsedDraft construction, sentence-index stability, trailing scope → NARROW (25 tests)
- [x] 02.2.1b Implement draft parser in `ingest/draft_parser.py`: parse_wikilinks(), strip_wikilinks(), detect_author_year(), split_sentences() (replicate pipeline NLTK logic), parse_draft() → NARROW (25 pass). Smoke-tested against ukraine-intro-test.txt: 9 sentences, "(Zeng 2026)" correctly flagged unparsed_citation.
- [x] 02.2.2a Write tests for citation binder (`tests/test_citation_binder.py`): single claim binding, multi-cite union semantics, citation-free claims, decomposed claims sharing original_index, trailing scope (sentence-only), DraftPosition populated, unparsed-citation status, out-of-range graceful handling → NARROW (15 tests)
- [x] 02.2.2b Implement citation binder in `ingest/citation_binder.py`: bind_citations(verdicts, parsed_draft) → List[ClaimRecord] → NARROW (15 pass)
- [x] 02.2.3 Sentence-index stability test included in test_draft_parser.py (test_sentence_index_stability) → NARROW
- [x] 02.2.4 TG 02.2 complete — regression check: 170 passed, 1 deselected (slow) → MID

### TG 02.3: Vault Serializer

New files: `ingest/vault_serializer.py`, `tests/test_vault_serializer.py`.
Evidence types to include: SOURCE, QUOTE, PARA, CLAIM, THESIS, OBS, RESULT, HYP, INT, EXP.
Non-evidence types excluded: DESIGN, SEED, FLEET, MOC, MS, EXAMPLE, COM.
Vault at `../ukraine-vote-analysis/vault-main/v-research/` (448 notes, 116 with argument_pyramid tag).

- [x] 02.3.1a Write tests for vault note parsing + serialization (`tests/test_vault_serializer.py`): frontmatter parsing, body section extraction, wikilink extraction, missing/malformed frontmatter graceful degradation, filtering by argument_pyramid, filtering by note type, token counting, budget warning, serialization output format → NARROW (22 tests). 6 fixture notes in `tests/fixtures/vault/v-research/`.
- [x] 02.3.1b Implement vault serializer in `ingest/vault_serializer.py`: VaultNote/SerializedVault types, parse_vault_note(), load_vault(), serialize_vault(), DEFAULT_EVIDENCE_TYPES → NARROW (22 pass). Key discovery: vault `type` field values differ from file prefixes (SOURCE→academic-paper/dataset/etc., QUOTE→quotation). `json.dumps(default=str)` handles YAML datetime.date fields.
- [x] 02.3.2 Live vault validation (2 tests, `@pytest.mark.slow`): 448 notes all parse (1 degrades to type:unknown — malformed YAML in SEED note, expected). argument_pyramid filter → 116 notes. Type counts spot-checked (≥100 SOURCE-subtypes, ≥30 quotation, ≥15 claim, ≥50 hypothesis).
- [x] 02.3.3 TG 02.3 complete — regression check: 192 passed, 3 deselected (slow) → MID

### TG 02.4: Cited-Claim Alignment

Architecture: cited note (any type) + one-hop linked notes → high-tier LLM alignment evaluation.
New files: `ingest/alignment.py`, `tests/test_alignment.py`.
Test file: `workspace/inbox/ukraine-rich-wikilinks-test.md` (7 wikilinks, 4 note types).

- [x] 02.4.0 Rename VaultVerdict `SOURCE_NOT_IN_VAULT` → `NOTE_NOT_IN_VAULT`; update claim-record-design.md, tests → NARROW (`pytest tests/test_claim_record.py`)
- [x] 02.4.1a Write tests for vault evidence gathering (`tests/test_alignment.py`): 8 tests — resolve cited note by name, one-hop traversal to linked notes, gather body content, handle note-not-in-vault, handle insufficient-vault-content, multiple note types (SOURCE→QUOTE, RESULT→HYP), linked-note-not-in-vault skipped, one-hop-only enforcement → NARROW
- [x] 02.4.1b Implement vault evidence gathering in `ingest/alignment.py`: `gather_evidence(note_name, vault_by_name)` → GatherResult with note content + one-hop linked note content, or verdict for missing/thin notes → NARROW
- [x] 02.4.2a Write tests for alignment evaluation (`tests/test_alignment.py`): 10 async tests — mock LLM call, evaluate claim against gathered evidence, verdict mapping to VaultVerdict, provenance recording, union semantics across cite set, LLM failure → graceful skip, no-web-verdict skip → NARROW
- [x] 02.4.2b Implement alignment evaluation in `ingest/alignment.py`: `evaluate_alignment(claim_record, vault_by_name)` → populates `vault_verdicts` on ClaimRecord; calls `get_llm(tier="high")` + `call_llm_with_structured_output()` → NARROW
- [x] 02.4.3 TG 02.4 complete — regression check: 210 passed, 3 deselected (slow) → MID (`pytest -m "not slow"`)
- [x] 02.4.4 Live spot-check on real draft claims using `ukraine-rich-wikilinks-test.md` + real vault → 3 vault_supported (RESULT, CLAIM, HYP notes with accurate provenance), 4 note_not_in_vault (correctly filtered by argument_pyramid/evidence_types). OpenRouter, 13 API calls.

### TG 02.5: Citation-Free Vault Matching

Architecture: two-stage — cheap batch-match call (one LLM call, all citation-free claims + serialized vault) → per-match verify at `high` tier.
New files: `ingest/vault_match.py`, `tests/test_vault_match.py`.
Reuses: `ingest/vault_serializer.py:serialize_vault()`, `ingest/alignment.py:gather_evidence()`.

- [x] 02.5.1a Write tests for batch matching (`tests/test_vault_match.py`): 5 tests — mock LLM returns proposals, skip cited claims, empty claims early-exit, LLM failure, skip no-web-verdict → NARROW
- [x] 02.5.1b Implement batch matching in `ingest/vault_match.py`: `batch_match_claims(records, serialized_vault)` → List[MatchProposal]; one LLM call at `mid` tier → NARROW
- [x] 02.5.2a Write tests for per-match verification (`tests/test_vault_match.py`): 9 tests — supported/contradicted/no_vault_match verdicts, out-of-range index, note-not-in-vault, LLM failure, claim_strength/evidence_quality copy from CLAIM notes (positive + negative cases) → NARROW
- [x] 02.5.2b Implement per-match verification in `ingest/vault_match.py`: `verify_matches(records, proposals, vault_by_name)` → populates vault_verdicts with route="vault_matched"; copies claim_strength/evidence_quality from matched CLAIM notes → NARROW
- [x] 02.5.3 TG 02.5 complete — regression check: 226 passed, 3 deselected (slow) → MID (`pytest -m "not slow"`)
- [x] 02.5.4 Live validation against ukraine vault → 15 batch proposals (mid tier), 9 verified vault_supported (high tier), claim_strength/evidence_quality copied from CLAIM notes. OpenRouter, same run as 02.4.4.

### TG 02.6: Gap Report v2

Architecture: `render_gap_report(records, manifest)` → report.md string; `serialize_results(records)` → JSON-serializable list.
New file: `ingest/gap_report.py`, `tests/test_gap_report.py`.
Assigns `suggested_action` from verdicts; renders per-claim details with provenance; vault-improvement signals section.

- [x] 02.6.1a Write tests for gap report (`tests/test_gap_report.py`): 14 tests — action assignment (7: supported→NONE, contradicted→REVISE, miscite→FIX_CITATION, web-only→ADD_VAULT_NOTE, free-unmatched→ADD_CITATION, unresolved, priority ordering), report rendering (5: summary table, claim details with provenance, vault improvement signals, no-vault-section when no vault, pipe escaping), serialization (2: round-trip, empty) → NARROW
- [x] 02.6.1b Implement `ingest/gap_report.py`: `assign_suggested_actions(records)`, `render_gap_report(records, manifest)`, `serialize_results(records)` — manifest-adaptive (omits vault sections when vault_path is None for light-profile compatibility) → NARROW
- [x] 02.6.2 TG 02.6 complete — regression check: 240 passed, 3 deselected (slow) → MID

### TG 02.7: Quality & Wrap

- [x] 02.7.1 MILESTONE: accepted via spot-check (user decision, Session 8) — the 02.4.4/02.5.4 live run exercised all code paths (alignment, matching, gap report) across 4 note types and both cited/citation-free flows; full-paper run judged unnecessary. Scale behavior (~450-claim batch matching) remains untested — acceptable risk, can run post-hoc if needed.
- [x] 02.7.2 Light-run regression: gap report with no vault → Phase 01-compatible output — verified by `test_report_no_vault_section_when_no_vault` (omits vault sections, shows "not configured")
- [x] 02.7.3 Update CLAUDE.md key files with new modules (Session 7); `docs-align-check` ran clean (Session 8: 46 paths verified, test counts match, no drift); HANDOVER.md updated and pushed (Session 8)

---

## Phase 03: Triage & Routing — APPROVED (user sign-off Session 8)

Plan: `phase-plans/phase-03-triage-and-routing.md`. Corpus RAG split out to Phase 04 (user decision, Session 8); router built as an extension point so Phase 04 and future routes (specialist DB searches) are additive. Web spend triage-gated. Milestone: routed heavy run on `workspace/inbox/ukraine-intro-test.txt`.

### TG 03.1: Triage Classifier

- [ ] 03.1.x Triage vocabulary documented in claim-record-design.md; batch classification (mid tier or below) populates triage_class / citation_expectation / importance; conservative-up on uncertainty; offline tests + characterized-file expectations (3 dataset-dependent claims classified as such)

### TG 03.2: Routing Policy and Route Registry

- [ ] 03.2.x Pure routing function (ClaimRecord × available_routes → decision), route-handler interface with web route as first implementation (per-claim claim_verifier reuse); extensibility proof test (fake route = stub handler + manifest declaration + policy-table row); routing table reviewed by user before milestone

### TG 03.3: Orchestration and Report Extension

- [ ] 03.3.x Production heavy-run entry point (parse → extract → bind → vault verify → triage → route → web) replacing spot-check demo wiring; gap report gains triage class, route taken, cost/route summary; manifest-adaptive sections; light-profile regression

### TG 03.4: Quality & Wrap

- [ ] 03.4.1 MILESTONE: routed heavy run on ukraine-intro-test.txt — 3 dataset-dependent claims route away from web; report judged useful by user
- [ ] 03.4.2 Light-profile regression; offline suite green; docs-align-check; CLAUDE.md/claim-record-design.md/TASKS.md/HANDOVER.md current; push to origin

Task breakdown within each TG is the implementing session's job (plan defines goals/success criteria/constraints; see activity-planning skill).

---

## Phases 04–06: Roadmap — FUTURE

- **Phase 04 — Corpus RAG Route:** doc-rag-backend as evidence route. First-client discovery of api.ragtogo.com (we own both repos, sole users — record client needs: DB content visibility, search by author+title/DOI/Zotero ref, API help/docs; improvements via direct edit + redeploy to Hetzner, or cross-repo communication note actioned by an agent in the doc-rag-backend repo; must not degrade other potential clients). Then client: `GET /search` scoped by `manifest.corpus_ids`, `"corpus"` route registered, high-tier evidence evaluation with document-id provenance.
- **Phase 05 — Deep Research Commissions:** human-approved escalation, commission writer, response-paper ingestion + re-evaluation
- **Phase 06 — Draft Update Loop:** propose citation-inserting draft edits after vault improvement

**Edge-case backlog:** PDF-only drafts / plain-text citation parsing; source fetching for absent papers; vault-less heavy runs; vault QA / chain completeness (verify vault notes against original sources — separate domain from draft-claim verification, likely reuses doc-rag-backend); semi-automated vault enrichment
