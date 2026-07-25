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

Amended Session 8 (user decision): TG 03.4 Evidence Summarization added (cheap-model extraction of claim-relevant content from raw search results before high-tier evaluation — user cost principle #1); Quality & Wrap renumbered 03.4 → 03.5.

### TG 03.1: Triage Classifier — COMPLETE

- [x] 03.1.1 Triage vocabulary documented in claim-record-design.md: TriageClass (trivial, general-factual, academic-citable, dataset-dependent, novel-result), CitationExpectation (expected, not-expected, optional), importance (1–5). Conservative-up rule: uncertain → non-trivial; uncertain between never-web and web-verifiable → web-verifiable.
- [x] 03.1.2 `ingest/triage.py`: `triage_claims()` — one mid-tier batch call over all claims, Literal-typed structured output, importance clamped 1–5 in code, omitted claims stay None (never default to trivial). 13 tests in `tests/test_triage.py`.
- [x] 03.1.3 Triage prompt tightened (Session 8 milestone review): dataset-dependent = author's own private data ONLY (not public records); explicit counter-examples (vote tallies, IGO records → general-factual); directional tie-break toward web-verifiable.

### TG 03.2: Routing Policy and Route Registry — COMPLETE

- [x] 03.2.1 `ingest/routing.py`: `decide_route()` (pure function, module-level POLICY table), `execute_routing()` (dispatches to registered handlers), web handler reuses claim_verifier graph per-claim. Policy: vault-resolved → stop; trivial → skip; novel-result/dataset-dependent → never web; general/academic/unclassified → web if available.
- [x] 03.2.2 ClaimRecord extended: `routing_decision`, `routing_reason`, `claim` (ValidatedClaim identity independent of web_verdict). `vault_verdicts` renamed to `route_verdicts` across codebase.
- [x] 03.2.3 Extensibility proof test: fake route (stub handler + manifest declaration + policy-table row) routes correctly. 28 tests in `tests/test_routing.py`.
- [x] 03.2.4 Routing table reviewed by user (Session 8) — approved without circuit-breaker.

### TG 03.3: Orchestration and Report Extension — COMPLETE

- [x] 03.3.1 `scripts/run_heavy.py`: production entry point. CLI: draft path + --vault + --argument-pyramid + --profile + --no-web. Composes: parse → extract (Claimify in-process) → bind_extracted_claims → vault verify (alignment + batch match + verify + fallback) → triage → routing → gap report. Outputs workspace/output/<stem>/results.json + report.md.
- [x] 03.3.2 Gap report extended: per-claim triage/routing fields, route summary (counts per decision, web calls avoided vs Phase 01 baseline), unparsed-citation count in header, vault-improvement signals for fallback matches ("consider adding argument_pyramid tag").
- [x] 03.3.3 Full-vault fallback for batch matching: one additional batch call (high tier, Session 8 user decision) against evidence-type-filtered full vault for claims unmatched by pass 1. Config-switchable (vault_match_fallback in config.toml, default on). Stale no_vault_match superseded when fallback finds match.
- [x] 03.3.4 Batch-match prompt amended: contradiction-seeking (same fact different number = match); keyword pre-filter surfaces priority candidates from vault.
- [x] 03.3.5 8 tests in `tests/test_orchestration.py`. 340 tests total (337 non-slow), all green.

### TG 03.4: Evidence Summarization — COMPLETE

- [x] 03.4.1 `claim_verifier/evidence_summarization.py`: `summarize_evidence_for_claim()` — reusable (claim_text + evidence items → condensed items). Mid tier. Preserves refuting content (prompted + safety: omitted sources keep raw text). URL attribution from originals by index (hallucinated URLs can't corrupt provenance). Fallback to raw on any failure.
- [x] 03.4.2 Config: `summarize_evidence` in config.toml (default true, off = byte-compatible). Pre-processing inside evaluate_evidence_node (not a separate graph node — avoids LangGraph reducer duplication).
- [x] 03.4.3 Token accounting: INFO log per claim (raw_chars, summarized_chars, raw_tokens_est, summarized_tokens_est, reduction%). Live results: 60–84% reduction. 19 tests in `tests/test_evidence_summarization.py`.

### TG 03.5: Pipeline Parallelization — COMPLETE

- [x] 03.5.1 `process_with_voting()`: all sentences vote concurrently (asyncio.gather across items). Voting logic (2/3 majority) unchanged.
- [x] 03.5.2 `execute_routing()`: all handler invocations concurrent with Semaphore(5). Policy decisions still sequential (pure, fast).
- [x] 03.5.3 `verify_matches()`: all per-proposal verifications concurrent with Semaphore(5).
- [x] 03.5.4 Wall-clock: ~13 min → ~4 min on standard test file (3.4x speedup). 340 tests, all green.

### TG 03.6: Quality & Wrap — IN PROGRESS

- [x] 03.6.1 MILESTONE: final routed heavy run on ukraine-intro-test.txt (Session 8) — 15 claims, 8 vault-resolved (including "98 votes" caught as vault_contradicted with 4 provenance notes), 7 web-checked (3 Supported, 3 Refuted, 1 Supported), 1 skip-trivial. Summarization: 60–84% reduction. Parallelization: ~4 min wall-clock. Tag-gap signals: 19 notes surfaced for argument_pyramid tagging.
- [x] 03.6.2 docs-align-check ran (Session 8 wrap); CLAUDE.md updated with Phase 03 modules, pipeline, quality gates; TASKS.md current; HANDOVER.md updated; pushed to origin.

Task breakdown within each TG is the implementing session's job (plan defines goals/success criteria/constraints; see activity-planning skill).

---

## Phase 04: Corpus RAG Route — COMPLETE (Session 10)

Plan: `phase-plans/phase-04-corpus-rag-route.md`. Backend repo cloned at `../doc-rag-backend` (Session 9 prep); API contract mapped from repo `main` — must be live-verified (`origin/dev` was 6 commits ahead at clone time).

### TG 04.1: First-Client Discovery (live)

- [x] 04.1.1 Read doc-rag-backend dev-branch HANDOVER — done (Session 9): migration 008 already applied to prod; env refactor merged to dev, not yet deployed (runtime-safe); Zotero corpus = 123 PDFs discovered, not yet ingested; auth = `DOC_RAG_API_KEY` in `/opt/doc-rag-backend/.env.production.local`, verbatim string compare, unset ⇒ auth bypassed; fresh key = `openssl rand -hex 32` + container recreate
- [x] 04.1.2 Live discovery against prod: `GET /health` verified (healthy, GROBID disabled). SSH access established (ed25519 key generated + authorized via Hetzner console). Fresh `DOC_RAG_API_KEY` provisioned and deployed (64-char hex, container recreated). `GET /documents` authenticated — prod had 1 test doc, no ukraine sources (eval seed is devtest-only, confirmed). 4 clean PDFs (Kim 2023, Nurullayev & Papa 2023, Zeng 2026, de Carvalho 2025) uploaded via SCP. Ingestion via `POST /documents` **FAILED** — backend's OpenAI key out of quota at embedding stage. Document rows created (d_OOfQK0u0hSFA, d_2IBOCexW_qQY, d_wERrWO7aNPBt, d_MWigEjhYX4xO) but all stages None. PDFs remain on server at `/data/pdfs/`; need OpenAI key topped up or embedding provider switched, then re-ingest.
- [x] 04.1.3 Environment decision recorded: prod (user-approved Session 9; devtest fallback only if prod lacks the documents)
- [x] 04.1.4 First client-needs note committed in doc-rag-backend: `docs-meta/client-needs/2026-07-24-claimeai-first-client-needs.md`, commit `463c155` pushed to origin/dev, HANDOVER pointer added. Covers: metadata-search gap, key-provisioning friction, content question. **Finding:** backend's own TASKS.md confirms the 5 eval docs (incl. all 3 ukraine sources) are FROZEN in **devtest only — prod DB has no ukraine sources**. Milestone live corpus leg therefore needs BOTH the API key AND a content decision (prod ingest vs devtest target) — both user-gated, recorded as Risk 1 materialized.

### TG 04.2: Corpus Client

- [x] 04.2.1a Write tests for corpus client (`tests/test_corpus_client.py`): 22 tests via httpx.MockTransport — request shape, header omitted when key unset, response parsing, flat-array pagination loop, conservative citation mapping (ambiguous → dropped), connection/401/500 → None → NARROW (red-first confirmed)
- [x] 04.2.1b Implement `ingest/corpus_client.py` — `search_corpus()`, `list_documents()` (accumulates partials on mid-loop failure), `map_citations_to_document_ids()`; schemas pinned from backend source (`app/models/`), main-vs-dev diff empty; httpx 0.28.1 already a transitive dep; no rerank params (L018) → NARROW (22 pass)
- [x] 04.2.2a Write tests for settings/config additions: `RAG_API_KEY` validation, `[corpus_api]` section loading → NARROW (6 new tests, red-first confirmed: `test_settings.py`, `test_config.py`)
- [x] 04.2.2b Implement settings field + `[corpus_api]` in config.toml + `.env.example` entry → NARROW (28 passed; `utils/config.py` needed no change — loads full TOML dict generically)
- [x] 04.2.3 TG 04.2 complete — regression check → MID: 366 passed, 3 deselected (Session 9)

### TG 04.3: Corpus Route Handler and Policy

- [x] 04.3.1 `CorpusVerdict` enum (`corpus_supported`, `corpus_contradicted`, `corpus_insufficient`, `no_corpus_hits`) + `provenance_type="corpus_doc_id"` recorded in `claim-record-design.md` ("Corpus Route (Phase 04, TG 04.3)" section), incl. deliberate scope line: corpus only for never-web claims this phase
- [x] 04.3.2a Tests written first (`tests/test_corpus_route.py`, 15 tests; +4 in `test_run_config.py`): verdict shape + provenance, factory wiring via handlers= override, never-web routes to corpus, manifest gating, API-down → None, high-tier assertion, single summarization + config switch → NARROW (red confirmed)
- [x] 04.3.2b Implemented `ingest/corpus_route.py`: `make_corpus_route_handler(corpus_ids)` factory (protocol/signature unchanged); route-local high-tier evaluator (claim_verifier's `VerificationResult` enum can't express insufficient — design finding: richer-vocabulary routes need route-local evaluation, alignment.py style); never-web `candidate_routes → ("corpus",)`; `available_routes` consults corpus_ids; small in-scope `_unverifiable_reason` tweak → NARROW (92 pass across 4 files)
- [x] 04.3.3 TG 04.3 complete — MID: 385 passed, 3 deselected; `ingest/gap_report.py` untouched (zero report-code changes — pillar 3 validated)

### TG 04.4: Orchestration and Milestone

- [x] 04.4.1 `run_heavy.py` corpus scoping: `--corpus-ids` CLI flag (comma-sep, whitespace-tolerant, blank → None), `_parse_corpus_ids()`, handler-dict wiring per corpus_route docstring contract (explicit `route_handlers` override still respected). 14 new tests in `test_orchestration.py` (red-first) → NARROW (23 pass) then MID (400 passed, 3 deselected)
- [x] 04.4.2 MILESTONE (SUPERSEDED by Phase 05 TG 05.5): Session 10 live run verified corpus infrastructure end-to-end (3 papers ingested, hybrid search confirmed, corpus route wired and available). No claims reached corpus because triage correctly classified all test-file claims as general-factual (Session 8 triage fix: vote tallies are public records). The original milestone criteria ("3 dataset-dependent claims receive corpus verdicts") was unsatisfiable — superseded by Phase 05's stronger milestone (three-tier cascade with source-conflict detection). Session 10 run: 16 claims, 11 vault-resolved, 5 web-checked, ~2 min, 23 Exa searches. Known errors caught: "98 votes" Refuted (correct: 93), "more than 40 countries" Refuted (correct: exactly 40).

### TG 04.5: Quality & Wrap

- [x] 04.5.1 docs-align-check + doc updates (Session 10)
- [x] 04.5.2 Cross-repo: null-byte ingestion failure note + repro PDF committed to doc-rag-backend (6fe1349, origin/dev); first client-needs note from Session 9 already pushed (463c155)
- [x] 04.5.3 HANDOVER.md updated; pushed to origin (Session 10)

---

---

## Phase 05: Three-Tier Evidence Cascade — COMPLETE (Session 12)

Plan: `phase-plans/phase-05-three-tier-evidence-cascade.md`. Reworks routing so vault, corpus, and web form a domain-general verification cascade. Adds citation-aware corpus scoping, importance-gated cross-checks (D4/D5), pure-code conflict detection with `source-conflict` and `vault-corpus-check-needed` flags. Supersedes Decision 44 ("corpus only for never-web").

TDD throughout: tests written first (red), then implementation makes them pass (green). Testing tiers: NARROW (targeted test file, 1–5s) during iteration; MID (`pytest -m "not slow"`, ~30s) at TG completion; FULL (entire suite) at milestone only.

Dependency order: TG 05.1 → 05.2 → 05.3 → 05.4 → 05.5.

### TG 05.1: Cascade Routing — COMPLETE

Normalization function (`normalize_verdict`) implemented here (needed for cascade decisions); reused by TG 05.4 for conflict detection.

- [x] 05.1.1a Write tests for `normalize_verdict()` — exhaustive mapping of every verdict string to support/refute/silent; unknown values → silent → NARROW (`tests/test_routing.py`)
- [x] 05.1.1b Implement `normalize_verdict()` in `ingest/routing.py` — pure function, D6 table, plus `_is_cascade_silent()` (only known-silent values trigger escalation, preserving extensibility) → NARROW
- [x] 05.1.2a Write tests for updated policy table — general row `candidate_routes=("corpus", "web")`; no-corpus manifest still routes to web directly → NARROW (`tests/test_routing.py`)
- [x] 05.1.2b Update POLICY general row to `("corpus", "web")` → NARROW
- [x] 05.1.3a Write tests for cascade in `execute_routing()` — vault-silent→corpus→support (stops); vault-silent→corpus-silent→web; never-web→corpus-silent→unverifiable; no-corpus manifest→web (today's behavior); handler failure→degrade to next tier with reason (synthetic `handler_error` verdict); handler returns None→degrade; _already_routed prevents double-routing; light profile byte-identical; max rounds safety bound; multi-record independence → NARROW (`tests/test_routing.py`, 33 new tests)
- [x] 05.1.3b Implement cascade in `execute_routing()` — multi-round decide→dispatch→check-silent loop with `_redecide()` helper; pre-count tracking for verdict detection; max 3 rounds → NARROW
- [x] 05.1.4 TG 05.1 complete — regression check → MID (60 routing tests pass)

### TG 05.2: Citation-Aware Corpus Scoping — COMPLETE

- [x] 05.2.1a Write tests for scoped corpus handler — cited claim with resolvable citations → scoped search; unresolvable citations → whole-scope fallback; citation-free → whole-scope; no-intersection fallback; scoped provenance_type `corpus_cited_doc`; no-hits path carries scoped type; backward compat with documents=None → NARROW (`tests/test_corpus_route.py`, 8 new tests)
- [x] 05.2.1b Update `make_corpus_route_handler()` factory to accept `documents` parameter; `_resolve_search_scope()` helper resolves cite_set→document_ids, intersects with corpus_ids → NARROW
- [x] 05.2.2a Write tests for corpus document pre-fetch and handler wiring in run_heavy.py → NARROW (`tests/test_orchestration.py`)
- [x] 05.2.2b Wire `list_documents()` pre-fetch + pass to factory in `scripts/run_heavy.py` → NARROW
- [x] 05.2.3 TG 05.2 complete — regression check → MID (106 tests across routing/corpus/orchestration). Fixed Phase 04 policy assertion (`test_policy_never_web_row_declares_corpus_candidate`) for TG 05.1 general row change.

### TG 05.3: Importance-Gated Cross-Checks (D4, D5) — COMPLETE

Cross-checks are post-routing steps: direct handler invocations that bypass the policy table. Function `apply_cross_checks()` in `ingest/routing.py`.

- [x] 05.3.1a Write tests for D4 attribution check — vault-resolved + cited + importance >= 4 + corpus-mapped → corpus check; importance < 4 → no check; citation-free → no check; corpus already routed → skip; no corpus handler → no crash → NARROW (`tests/test_routing.py`, 5 tests)
- [x] 05.3.1b Implement D4 in `apply_cross_checks()` via `_needs_d4()` gate → NARROW
- [x] 05.3.2a Write tests for D5 refutation confirmation — single-tier refute + importance >= 4 + web-eligible → web check; importance < 4 → no check; support never triggers; never-web → no check; web already exists → skip; corpus refute also triggers; web refute → no further check → NARROW (`tests/test_routing.py`, 7 tests)
- [x] 05.3.2b Implement D5 in `apply_cross_checks()` via `_needs_d5()` gate → NARROW
- [x] 05.3.3b Wire `apply_cross_checks()` in run_heavy.py between execute_routing and assign_suggested_actions → NARROW
- [x] 05.3.4 TG 05.3 complete — regression check → MID (96 tests across routing + orchestration)
- [x] 05.3.5 (Amendment, Session 12) D10 support-confirmation: tests + implementation + config switch
- [x] 05.3.6 (Amendment, Session 12) conflict-demo fixture at tests/fixtures/conflict-demo/
- [x] 05.3.7 (Amendment, Session 12) Alias-based cited-note resolution: `aliases` frontmatter parsed, `build_vault_index()` (filename wins, ambiguous aliases dropped), wired into run_heavy + spot_check. Vault-side lint (every SOURCE note carries an "Author Year" alias) is the sibling-repo's job.

### TG 05.4: Conflict Detection, Flags, and Report — COMPLETE

All runtime code in this TG is pure (zero LLM calls). Uses normalization from TG 05.1.

- [x] 05.4.1a/b `conflict_flags: List[str]` field added to ClaimRecord (default empty). 2 tests in `tests/test_claim_record.py` → NARROW
- [x] 05.4.2a/b `detect_conflicts()` pure function in `ingest/gap_report.py` — `_normalized_verdicts_for_routes()` + `_opposing()` helpers; `SHARED_LINEAGE_ROUTES`, `VAULT_ROUTES`, `WEB_ROUTE`, `CORPUS_ROUTE` constants. 8 tests in `tests/test_gap_report.py` → NARROW
- [x] 05.4.3a/b `assign_suggested_actions()` updated: `source-conflict` in conflict_flags → REVISE_CLAIM as top priority (before vault_contradicted). 1 test → NARROW
- [x] 05.4.4a/b Gap report extensions: `_render_source_conflict()` per-claim block with shared vs web provenance; vault-corpus mismatch subsection in Vault Improvement Signals; `_is_single_lineage()` derives D8 at render time; all gated on has_vault (light profile unchanged). 4 tests → NARROW
- [x] 05.4.5 Update `docs/playbook/claim-record-design.md` — normalization table, both flags, single-lineage, superseded scope line, lineage groups, cross-check gates, assign_suggested_actions priority update
- [x] 05.4.6 TG 05.4 complete — MID regression: 468 passed, 3 deselected

### TG 05.5: Milestone and Wrap — COMPLETE (Session 12)

- [x] 05.5.1 Full test suite green → FULL: 471 passed, 0 failed (Session 11); 488 passed after Session 12 amendments (D10 + alias resolution + fixtures)
- [x] 05.5.2a MILESTONE (live, 3 runs): cascade demonstrated — Run 3 (correct vault config): 17 claims, 11 vault-resolved, 5 corpus, 1 web. ~2 min wall-clock. Cascade corpus→web demonstrated on 1 claim. Single-lineage annotations on corpus-only claims.
- [x] 05.5.2b MILESTONE (Session 12): source-conflict flag demonstrated live via D10 amendment + conflict-demo fixture (`tests/fixtures/conflict-demo/`: tiny committed vault with planted "140 votes" error, draft repeating it). Run: vault_supported → D10 web confirmation → web Refuted (real tally: 141) → `source-conflict` flag + REVISE-CLAIM rendered in gap report. Also: cited-file run (ukraine-intro-cited-test.md) demonstrated citation-aware corpus scoping live (16 claims, 8 vault / 4 corpus / 4 web, ~2 min). The original D4-only path to source-conflict was superseded by D10 (user decision, Session 12).
- [x] 05.5.3a CLAUDE.md pipeline section updated with cascade. claim-record-design.md updated with Phase 05 section.
- [x] 05.5.3b `docs/websearch-and-costs.md` updated (Session 12): corpus cost profile (~$0.01–0.02/claim, no search charge), Session 12 live run data, D10 cost impact (~2x web calls), Exa credit-cap correction ($20 sign-up + $10/month, hard cap — 402 observed live), zero-evidence verdict caveat.
- [x] 05.5.4 HANDOVER.md updated; pushed to origin (Sessions 11 and 12)

Session 12 findings for the backlog (recorded below): web evaluator returns "Refuted" on zero evidence; gap-report web-call counter misses D4/D5/D10 cross-check calls; Exa credits exhausted mid-session (config flipped to tavily for the demo run, reverted to exa at close).

---

## Session 13: Backlog Maintenance — COMPLETE (Session 13)

Clears the four high-value backlog items before Phase 06 planning. Not a phase — one-session maintenance recorded here at task level (no separate phase-plan file). TDD throughout: red first, then green. Tiers: NARROW during iteration, MID at TG completion, FULL once before the wrap commit.

### TG M1: Zero-Evidence Web Verdicts (correctness bug)

Root cause: `VerificationResult` enum lacks INSUFFICIENT/CONFLICTING (commented out in `claim_verifier/schemas.py`); evaluator prompt already offers both strings, so LLM answers hit the `ValueError` catch in `evaluate_evidence.py` and silently default to REFUTED. Same default on LLM failure. Empty evidence list goes to the LLM as "no snippets found" prose. CLAUDE.md already documents the 4-verdict vocabulary — code catches up to docs. `routing.py:_VERDICT_MAP` already maps both new strings → silent (no cascade change needed).

- [x] M1.1a Failing tests written first in NEW `tests/test_evaluate_evidence.py` (10 tests; red confirmed: 9/10 failed pre-implementation) → NARROW
- [x] M1.1b Implemented: INSUFFICIENT + CONFLICTING added to `VerificationResult` (exact strings match `_VERDICT_MAP`); empty-evidence guard returns INSUFFICIENT with NO LLM call; LLM-failure fallback and unparseable-verdict default both REFUTED → INSUFFICIENT → NARROW (21 pass incl. evidence-summarization file)
- [x] M1.2a/b `generate_report.py` count dict now built from all `VerificationResult` members; summary appends insufficient/conflicting only when nonzero → NARROW
- [x] M1.3 Gap-report fall-through pinned: web INSUFFICIENT/CONFLICTING → ADD_CITATION (citation-free) / UNRESOLVED (cited), never ADD_VAULT_NOTE (4 tests, behavior already correct) → NARROW
- [x] M1.4 TG M1 complete — regression → MID (519 passed)

Acceptance: a dead search provider (empty evidence) can no longer produce a Refuted verdict; no live run needed (unit-provable).

### TG M2: Gap-Report Web-Call Counter (reporting bug)

`_render_route_summary` counts only `routing_decision`; D4/D5/D10 cross-checks append to `route_verdicts` without touching it (conflict-demo said "0 web calls" while making 9).

- [x] M2.1a Failing tests written first in `tests/test_gap_report.py` (9 tests incl. conflict-demo shape 0-routing/9-cross-check reproduction, handler_error counting, no-double-count; red confirmed) → NARROW
- [x] M2.1b Implemented `_route_call_counts()` in `ingest/gap_report.py`: counts from `route_verdicts` (ground truth for invocations); report lines now "Web calls made this run: N (X via routing, Y via cross-checks)" + corpus line when nonzero + invocations-vs-searches caveat → NARROW (40 pass)
- [x] M2.2 TG M2 complete — regression → MID (519 passed)

Acceptance: unit tests reproduce the conflict-demo shape (0 routing-decision web calls + 9 cross-check verdicts) and the report shows 9. No live rerun (would cost ~9 web calls for no added confidence).

### TG M3: Triage Importance Recalibration (cost control)

Prompt gives importance one unanchored line while other axes get worked examples — clusters at 4+, so D10 fires on ~all vault-resolved claims. Session 12 user decision on the ≥4 gate VALUE stands; this TG fixes the input distribution and makes the threshold configurable without changing its default.

- [x] M3.1a Failing tests written first in `tests/test_triage.py` (5 tests: rubric anchors, distribution guidance, anti-inflation, Field mirror, core-data carve-out; red confirmed) → NARROW
- [x] M3.1b Anchored rubric implemented in `TRIAGE_SYSTEM_PROMPT` + Field description (5 thesis-carrying … 1 incidental; "most claims are 2–3" anchor; anti-inflation warning) → NARROW
- [x] M3.1c (user decision, Session 13) Core-data carve-out: quantitative claims reporting the core data the draft's analysis rests on (e.g. vote tallies in a voting-analysis paper) rate 4; incidental figures (population shares, date spans, section counts) stay 2–3. First spot-check had dropped tallies to 3, which would have removed D10 coverage from the exact planted-error scenario D10 was built for → NARROW (18 pass)
- [x] M3.2a/b `cross_check_importance_threshold` config-driven in `[pipeline]` (default 4, behavior unchanged); gate tests monkeypatch the module constant per SUPPORT_CONFIRMATION_ENABLED pattern → NARROW (111 pass across triage/config/routing)
- [x] M3.3 Live spot-check ×2 (one mid-tier call each, 0 searches) on standard test file claims: pre-carve-out 9/17 ≥4 (tallies dropped to 3 — flagged to user); post-carve-out 12/17 ≥4 with tallies restored to 4, single 5 (was three 5s), incidental figures at 3. Old baseline: 14/17. Accepted.
- [x] M3.4 TG M3 complete — regression → MID (520 passed)

### TG M4: Zeng 2026 Corpus ID + Docs (config/docs)

Sibling repo fixed null-byte bug (PUA chars from Docling), re-ingested Zeng 2026: `d_ZikkNbPZFWWV` (all stages complete). No pipeline code change — IDs are CLI-passed.

- [x] M4.1 Live-verified: `d_ZikkNbPZFWWV` in prod `list_documents()` AND hybrid search scoped to it returns 10 on-topic chunks (first hit: UN resolutions table). Also observed: 4 dead Session-9 document shells + 2 ArXiv test docs still in prod DB — cleanup noted for sibling repo.
- [x] M4.2 Updated: HANDOVER.md (corpus table + 4-ID real-vault command + Session 13 summary), phase-05 plan (Risk 1 resolved, Zeng dependency updated), websearch-and-costs.md (zero-evidence fixed, D10 recalibration), claim-record-design.md (web route emits INSUFFICIENT/CONFLICTING)
- [x] M4.3 Session wrap: FULL suite 523 passed; HANDOVER.md + TASKS.md updated; committed

---

## Phases 06–08: Roadmap — FUTURE

- **Phase 06 — Claude-Native Web Search:** Replace Exa/Tavily with a Claude Code search provider that uses WebSearch + WebFetch (included in the $200/mo Max plan). Eliminates two external search API dependencies. Direction: reverse-engineer Exa/Tavily search-and-extract flows, build a `claude` search provider behind the existing `search_provider` config switch, spike on the standard test file against Exa baseline verdicts. Key tradeoff: speed (~1s API calls → ~15–30s sub-agent calls; acceptable for research tool, not real-time). Approach: start with Option 3 (direct tool-use via Anthropic API, no sub-agent overhead) before falling back to sub-agent orchestration. The `web-interaction` skill documents 7 available methods — WebSearch + WebFetch is the primary path; playwright-cli / Chrome MCP are fallbacks for JS-heavy or Cloudflare-blocked pages.
- **Phase 07 — Deep Research Commissions:** human-approved escalation for unresolvable claims, commission writer, response-paper ingestion + re-evaluation (was Phase 06 before the search-provider pivot)
- **Phase 08 — Draft Update Loop:** propose citation-inserting draft edits after vault improvement

**Edge-case backlog:** PDF-only drafts / plain-text citation parsing; source fetching for absent papers; vault-less heavy runs; vault QA / chain completeness (verify vault notes against original sources — separate domain from draft-claim verification, likely reuses doc-rag-backend); semi-automated vault enrichment; vault-side aliases lint (every SOURCE note carries an "Author Year" alias so hand-written wikilinks resolve — ClaimeAI side landed Session 12 as `build_vault_index()`); sibling-repo prod-DB cleanup (4 dead Session-9 document shells + 2 ArXiv test docs observed Session 13); retrieve_evidence still can't distinguish search-API errors (e.g. 402) from genuine zero results — both return empty evidence and now yield INSUFFICIENT (correct verdict since Session 13, but error-vs-empty telemetry would help spot dead providers faster)

Cleared Session 13 (see Session 13: Backlog Maintenance above): zero-evidence Refuted bug; gap-report web-call undercount; triage importance recalibration + configurable cross-check threshold; Zeng 2026 corpus ID (`d_ZikkNbPZFWWV`).
