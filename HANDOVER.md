# Session Handover

**Last Updated:** 2026-07-25 (Session 15, outgoing)
**Current Status:** All phases through 05 COMPLETE. Phase 06 DEFERRED (Session 15, D60). No code changes this session — research and documentation only (6 commits). Exa credits being purchased for interim use; Tavily free tier as fallback. Future search-provider build recorded in `project-management/phase-plan-notes/phase-06/phase-06-search-provider-decision.md`.

---

## Start Here

**Outgoing session completed:** Session 15 — Phase 06 search-provider research. No code changes. Six docs commits, cross-repo updates (control-hub IDEA note, web-interaction skill update).

1. **Claude-native search direction rejected (D60).** Anthropic API `web_search` ~$10/1k (more than Exa's $7/1k). Headless Claude Code / `claude -p` expected to bill user credits, not plan allowance. Both paths dead.

2. **Market scan conducted (July 2026).** Seven providers compared: Exa ($7/1k, content), Tavily ($8/1k, content), Serper ($1/1k, snippets), Brave ($3–5/1k, snippets), Jina (token-priced), SearXNG ($0, self-hosted), PixSerp ($1.50–3.50/1k, synthesized + snippets). Structural finding: every cheap option is snippet-only; every content-included option costs $7–8/1k — except PixSerp which returns cited snippets at $1.50–3.50/1k.

3. **PixSerp evaluated live (32 API calls).** Results in `docs/websearch-and-costs.md`:
   - **Strengths:** Handles specific-entity queries that Tavily fails (claim 2, ES-11/1 vote count — 3 independent sources found). Fast (1.3–3.4s). At $1.50/1k, 4.7× cheaper than Exa.
   - **Weaknesses:** Returns synthesized answers, not raw page content. Deep tier hallucinated on claim 5 (confidently wrong). Weak on refutation (claim 3, planted error — no counter-figure found, unlike Tavily which found "93"). `response_format` structured output returns 502 (broken/undeployed).
   - **Conclusion:** PixSerp could replace Exa (using citation `snippet` fields as evidence, discarding the synthesized answer) **or** serve as the SERP step in a two-stage design. **Cannot replace Tavily's full-page depth on its own.**

4. **Query-design playbook written** (`docs/playbook/query-design.md`). Three query shapes documented (leading, open factual, keyword neutral) with worked examples. Open factual recommended as default — the mid-tier summarization step handles noise, and leading queries risk verification bias that causes wrong verdicts.

5. **crawl4ai service explored** (user's Railway deployment verified live). Full capability documented — BM25 content filtering, stealth escalation, 26 endpoints. Recorded as a reference in project memory and control-hub vault IDEA note for generalising the two-stage capability.

6. **RAGAS benchmark reference recorded.** Emergent Methods 2024 article (AskNews, JinaAI, Tavily, Exa on RAGAS context_precision) — open-source code available for self-run evaluation.

**Incoming session should:**

1. **Buy Exa credits** if not already done. The committed config default (`search_provider = "exa"`) is correct; the 402 errors clear once the account has credit. Tavily free tier (1k/month) is the zero-cost fallback.
2. **Decide what to work on.** Phase 06 implementation is deferred. The pipeline (Phases 01–05) is functionally complete — 523 tests, live-verified cascade. Options for the next session:
   - Use the pipeline on real work (fact-check a draft)
   - Phase 07 (deep research commissions) or Phase 08 (draft update loop)
   - PixSerp integration as a cheap Exa alternative (narrow scope: add a `"pixserp"` case to `retrieve_evidence.py`, use citation snippets as Evidence, add `PIXSERP_API_KEY` to settings)
   - Investigate claim 3 ground truth — the Feb 2025 UNGA session had multiple resolutions; "98 votes" may be correct for one of them (A/RES/ES-11/9), making our "planted error" annotation ambiguous
3. **If implementing PixSerp:** read the integration surface summary below (unchanged from Session 14) and `docs/playbook/query-design.md` for prompt-phrasing guidance. The key design choice: use `pixserp-fast` citation snippets as `Evidence.text` (discard synthesized answer), or use citation URLs + crawl4ai fetch for full-page content.

**Integration surface summary (unchanged from Session 14, still valid for any new provider):**

| File | What to change |
|------|---------------|
| `claim_verifier/nodes/retrieve_evidence.py` | Add `SearchProviders.pixserp()` method + `"pixserp"` case in `_search_query()` dispatch |
| `config.toml` | Add `search_provider = "pixserp"` option |
| `utils/cost_tracking.py` | Add `"pixserp"` to cost estimates ($0.0015–0.0035/call) |
| `utils/settings.py` | Add `PIXSERP_API_KEY` field (pxs_ prefix, 40 hex chars) |
| `.env.example` | Already done (Session 15) |

**No changes needed downstream:** query generation, evidence summarization, evaluation, routing/cascade, gap report, triage — all provider-agnostic. But read `docs/playbook/query-design.md` — the query generation prompt (`QUERY_GENERATION_INITIAL_SYSTEM_PROMPT`) currently biases toward leading/keyword queries; revising it to open factual form would improve all providers.

**Key docs produced this session:**
- `project-management/phase-plan-notes/phase-06/phase-06-search-provider-decision.md` — full decision record, market scan, PixSerp test results (5-claim + 27-call matrix), deferred two-stage design, work items
- `docs/websearch-and-costs.md` — PixSerp section added (pricing tiers, live test data, content depth comparison, integration assessment)
- `docs/playbook/query-design.md` — new playbook: claim-to-query transformation, verification bias, three query shapes

**Critical config notes for heavy runs:**
- `--vault` path must be the vault ROOT (`vault-main`), NOT `vault-main/v-research` — `load_vault()` appends `v-research` internally. Wrong path silently produces zero vault notes.
- `--argument-pyramid` value must be `un-ukraine-russia-war-votes-working-paper` for the real vault.
- Real-vault command (4 corpus papers): `poetry run python scripts/run_heavy.py workspace/inbox/ukraine-intro-cited-test.md --vault "PATH/vault-main" --argument-pyramid un-ukraine-russia-war-votes-working-paper --corpus-ids d_o3qBk5fESO_q,d_7ZUo22uPGdsf,d_7lRaRsrtAJOW,d_ZikkNbPZFWWV`

**Phase plans:** `phase-02` through `phase-05` all COMPLETE. Phase 06 DEFERRED — decision record at `project-management/phase-plan-notes/phase-06/phase-06-search-provider-decision.md` (no implementation plan yet).

---

## Current Context

### Repo structure

Agent packages at root: `claim_extractor/`, `claim_verifier/`, `fact_checker/`, `utils/`, `security/`, `scripts/`, `ingest/`. No `apps/` directory. `docs/playbook/` for decision rationale. Sibling repos: `../doc-rag-backend` (cloned Session 9), `../ukraine-vote-analysis` (vault + source PDFs).

### Configuration

**`config.toml`** — non-sensitive pipeline config. Sections: `[pipeline]` (llm_provider, search_provider, results_per_query, max_search_iterations, summarize_evidence, vault_match_fallback, support_confirmation, cross_check_importance_threshold), `[models.*]` (tier->model mapping per provider), `[reasoning.*]` (reasoning effort per provider/tier), `[corpus_api]` (base_url, mode, top_k).

**`.env`** — secrets only: `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `EXA_API_KEY`, `TAVILY_API_KEY`, `REDIS_URI`/`REDIS_URL`, `RAG_API_KEY`.

### Environment

| Component | Detail |
|-----------|--------|
| Python | 3.11.15 via uv |
| Poetry | 2.4.1 via `uv tool install poetry` |
| Venv | `C:\vpy\claime-agent-j1KWVyi4-py3.11` |
| Dev server | `poetry run dev` (light profile only) |
| Heavy runs | `poetry run python scripts/run_heavy.py` (in-process, no dev server needed) |
| SSH to Hetzner | `ssh -p 49152 root@135.181.196.207` (ed25519 key at `~/.ssh/id_ed25519`, authorized Session 9) |

### API keys configured (.env at repo root)

All present: `OPENAI_API_KEY` (sk-proj-, topped up Session 10), `EXA_API_KEY` (UUID, verified live), `OPENROUTER_API_KEY` (sk-or-v1, verified live), `TAVILY_API_KEY` (tvly-dev-, verified live), `REDIS_URI` + `REDIS_URL` (both redis://localhost:6379, Redis optional for local dev), `RAG_API_KEY` (64-char hex, provisioned Session 9, verified live), `PIXSERP_API_KEY` (pxs_, added Session 15, verified live — 32 API calls made).

### Model tier mapping (current, from config.toml)

| Tier | OpenAI | OpenRouter | Reasoning |
|------|--------|------------|-----------|
| low | gpt-4o-mini | google/gemma-4-26b-a4b-it | -- |
| mid | gpt-4.1-mini | anthropic/claude-haiku-4.5 | -- |
| high | gpt-4.1 | anthropic/claude-sonnet-5 | medium |

### What was verified live

| Test | Provider | Search | Result |
|------|----------|--------|--------|
| Session 2 | OpenAI | Exa | 14 claims, 12 supported, 2 refuted |
| Session 3 | OpenRouter | Exa | 2 claims, 2 supported |
| Session 3 | OpenRouter | Tavily | 3 claims, 3 supported |
| Session 4 | OpenAI | Exa | 448 claims (ukraine paper), ~$10 cost |
| Session 5 | OpenAI | Exa | FAILED (429 insufficient_quota) |
| Session 5 | OpenRouter | Exa | 15 claims (ukraine-intro-test.txt), 10 supported / 5 refuted |
| Session 7 | OpenRouter | -- | Vault alignment + matching spot-check: 3 vault_supported, 9 vault_supported (matching), 4 note_not_in_vault. 13 API calls. |
| Session 8 run 1 | OpenRouter | Exa | Phase 03 milestone (pre-triage-fix): 15 claims, 3 web / 12 unverifiable. |
| Session 8 run 2 | OpenRouter | Exa | Post-triage-fix: 15 claims, 14 web / 1 trivial. "98 votes" Refuted by web. |
| Session 8 run 3 | OpenRouter | Exa | Post-parallelization: 11 claims (extraction variance), ~4 min. |
| Session 8 run 4 (final) | OpenRouter | Exa | 15 claims, 8 vault-resolved / 7 web. "98 votes" caught by vault. ~4 min. |
| Session 9 | -- | -- | api.ragtogo.com: `/health` verified, `/documents` authenticated. 4 PDFs uploaded + ingestion FAILED (backend OpenAI key out of quota). |
| Session 10 | OpenAI | Exa | Phase 04 milestone: 16 claims, 11 vault-resolved, 5 web-checked. Corpus wired but 0 claims routed to it. |
| Session 11 | OpenAI | Exa | Phase 05 milestone: 17 claims, 11 vault-resolved, 5 corpus, 1 web (cascade: corpus→web). ~2 min. Source-conflict not triggered (no cited claims in test file). |
| Session 12 run 1 | OpenAI | Exa | Cited-file milestone (ukraine-intro-cited-test.md): 16 claims, 8 vault, 4 corpus (citation-scoped search live), 4 web. ~2 min, ~18+ searches ≈ $0.13. Exa credits exhausted later this session. |
| Session 12 run 2 | OpenAI | Exa (dead) | Conflict-demo first attempt: every search 402 NO_MORE_CREDITS → zero-evidence "Refuted" verdicts (bug logged). Run discarded. |
| Session 12 run 3 | OpenAI | Tavily | Conflict-demo (fixture vault, D10 active): 9 claims all vault-resolved, 9 D10 web confirmations, planted "140 votes" error caught — web Refuted (141) → `source-conflict` + REVISE-CLAIM in report. MILESTONE 05.5.2b met. |

### Key decisions made

1–50: See Session 10 handover (preserved in git history).
51. **Vault `argument_pyramid` tag renamed** (Session 11 discovery). Vault notes changed from `ukraine-vote` to `un-ukraine-russia-war-votes-working-paper`. CLI `--argument-pyramid` must match current vault frontmatter exactly — mismatch silently loads zero notes.
52. **`load_vault()` path convention** (Session 11 discovery). Pass the vault ROOT (e.g. `vault-main`), not the research subdirectory. The function appends `v-research` internally. Wrong path silently produces zero vault notes (no error raised).
53. **Source-conflict requires cited claims** (Session 11 finding). D4 attribution check (the only path to both corpus and web verdicts on the same claim) requires `citation_status == CITED`. Citation-free test files can demonstrate the cascade but not the conflict flags. SUPERSEDED by Decision 54: D10 opens a citation-free path to source-conflict.
54. **D10 — support confirmation** (Session 12, user decision). Vault/corpus-supported + importance ≥ 4 + web-eligible → one web confirmation. Reverses Session 10's "supports never trigger cross-checks" guardrail per verification-conservatism principle. User chose ≥ 4 gate over recommended ≥ 5, accepting ~2x web calls. `support_confirmation` config switch (default true).
55. **Alias-based note resolution** (Session 12, user decision). Wikilink targets resolve via `build_vault_index()`: filename stem + frontmatter `aliases`. Filename wins; ambiguous aliases dropped entirely. Vault-side lint (SOURCE notes carry "Author Year" aliases) is the sibling repo's job.
56. **Exa free tier is a hard credit cap** (Session 12 verified). $20 sign-up + $10/month refresh, $7/1k searches; 402 NO_MORE_CREDITS when exhausted. Rate limits are separate. Committed config default stays `exa` (user decision); flip to `tavily` locally during outages.
57. **Core-data carve-out for importance rubric** (Session 13, user decision). Quantitative claims reporting the core data the draft's analysis rests on (e.g. vote tallies in a voting-analysis paper) rate importance 4 (directly load-bearing) even though the argument might survive any single figure being wrong. Incidental figures (population shares, date ranges, section counts) stay 2–3. Rationale: first spot-check with the anchored rubric dropped tallies to 3, which would have removed D10 coverage from the exact planted-error scenario D10 was built for.
58. **`cross_check_importance_threshold` is now configurable** (Session 13). Default 4 unchanged (user Session 12 decision). Raise to 5 to tighten cost control; lower to widen confirmation coverage. Config key: `[pipeline] cross_check_importance_threshold`.
59. **Phase 06 orchestration: Fable + goal-loop** (Session 14, user decision). Use Fable as orchestrator model. Define success criteria from comparator set (5 claims with expected verdicts). Sub-agents implement, verification agents check criteria, loop on failure until criteria met. Three evaluation metrics: speed (incl. parallelisation ceiling), quality/accuracy (verdict match rate), cost ($0 marginal search + LLM tokens).
60. **Phase 06 deferred; two-stage provider is the future build** (Session 15, user decision). Claude-native search rejected (API web_search ~$10/1k > Exa $7/1k; `claude -p` expected to bill user credits, not Max allowance). No drop-in cheaper content-included provider exists — future build is Serper SERP (~$1/1k) + user's crawl4ai Railway service (BM25 content filter, $0 marginal) behind the `search_provider` switch. Full record: `project-management/phase-plan-notes/phase-06/phase-06-search-provider-decision.md`. Interim: buy Exa credits; Tavily free tier fallback. Goal-loop evaluation approach (D59) unchanged when the build happens.

### Test suite

523 tests total (520 pass with `-m "not slow"`, 3 slow tests). Session 13 added 32: 10 (test_evaluate_evidence.py, new), 13 (test_gap_report.py), 6 (test_triage.py), 2 (test_config.py), 3 (test_routing.py). Note: 2 were adjustments to existing test counts for generate_report.py coverage inside test_evaluate_evidence.py.

| File | Count | Covers |
|------|-------|--------|
| test_models.py | 24 | MODEL_REGISTRY, tier resolution, provider routing, reasoning effort |
| test_settings.py | 18 | Pydantic settings, env var validation, RAG_API_KEY |
| test_ingest.py | 31 | PDF extraction, chunking, text dispatch, report rendering |
| test_cost_tracking.py | 12 | Search cost counter, estimates, free-tier balance, print_summary |
| test_config.py | 12 | TOML loading, sections, fallbacks, real config.toml validation, corpus_api, cross_check_importance_threshold |
| test_claim_record.py | 28 | ClaimRecord, enums incl. CorpusVerdict, conflict_flags, DraftPosition, RouteVerdict, serialization |
| test_run_config.py | 24 | ResourceManifest, RunProfile, available_routes incl. corpus, vault-less degradation |
| test_draft_parser.py | 25 | Wikilink parsing, stripping, author-year detection, sentence splitting, ParsedDraft |
| test_citation_binder.py | 15 | Citation binding via original_index, union semantics, decomposition survival |
| test_vault_serializer.py | 35 | Vault note parsing, filtering, serialization, token counting, alias parsing, build_vault_index collision handling, conflict-demo fixture guard (33 narrow + 2 slow) |
| test_alignment.py | 23 | gather_evidence (8 + 1 alias resolution), evaluate_alignment (12 + 2 fallback) |
| test_vault_match.py | 42 | batch_match_claims, verify_matches, fallback, supersede, keywords, contradiction |
| test_evaluate_evidence.py | 10 | VerificationResult enum (4 members), empty-evidence guard, LLM-failure→INSUFFICIENT, generate_report summary |
| test_gap_report.py | 46 | assign_suggested_actions (incl. INSUFFICIENT/CONFLICTING pin), render_gap_report, serialize_results, detect_conflicts, source-conflict rendering, single-lineage annotation, route-call counter (cross-check breakdown) |
| test_triage.py | 18 | Batch triage, conservative fallback, importance clamping, anchored rubric, core-data carve-out, prompt content |
| test_routing.py | 83 | Policy rows, cascade (normalize_verdict, execute_routing multi-round), D4/D5/D10 cross-checks, configurable threshold, extensibility proof |
| test_evidence_summarization.py | 11 | On/off switch, extract mapping, refuting content, fallback paths |
| test_corpus_client.py | 22 | Search request/response, pagination, citation mapping, degradation |
| test_corpus_route.py | 23 | Handler verdicts, provenance, factory wiring, citation-aware scoping, manifest gating |
| test_orchestration.py | 25 | Pipeline composition, no-vault degrade, corpus wiring with documents, CLI parsing, cross-checks wiring |
| test_ingest.py (slow) | 1 | Docling PDF extraction (~16s) |

### Session 13 modified files (Backlog Maintenance)

| File | Changes |
|------|---------|
| `claim_verifier/schemas.py` | +2 lines: `INSUFFICIENT`, `CONFLICTING` enum members on `VerificationResult` |
| `claim_verifier/nodes/evaluate_evidence.py` | Empty-evidence guard (skip LLM call → INSUFFICIENT); failure/fallback defaults REFUTED → INSUFFICIENT |
| `fact_checker/nodes/generate_report.py` | Count dict built from all `VerificationResult` members; summary reports all nonzero verdicts |
| `ingest/gap_report.py` | `_route_call_counts()` counts from `route_verdicts`; cross-check breakdown in report |
| `ingest/triage.py` | Anchored 1–5 importance rubric + distribution guidance + core-data carve-out |
| `ingest/routing.py` | `CROSS_CHECK_IMPORTANCE_THRESHOLD` now config-driven (3 lines changed) |
| `config.toml` | `cross_check_importance_threshold = 4` added to `[pipeline]` |
| `docs/websearch-and-costs.md` | Zero-evidence caveat → fixed; D10 cost recalibration note |
| `docs/playbook/claim-record-design.md` | D6 table: web route now emits INSUFFICIENT/CONFLICTING (Session 13 note) |
| `project-management/phase-plans/phase-05-...md` | Risk 1 resolved; Zeng 2026 dependency updated |

### Hetzner / doc-rag-backend state (updated Session 13)

| Item | Status |
|------|--------|
| Server | `ubuntu-8gb-hel1-1`, healthy, SSH on port 49152 |
| Compose dir | `/home/app/doc-rag-backend/code/` |
| App container | `code-app-1`, healthy |
| Supabase prod | `prod-ragtogo` (ref `rmxgiszgfycfwlfurdvu`) |
| Pinecone prod | `doc-rag-prod` (1536 dims, serverless) |
| DOC_RAG_API_KEY | Provisioned Session 9 (64-char hex) |
| Ingestion | All 4 papers ingested (Zeng 2026 null-byte fix landed Session CA) |
| Metadata filters | Live — `GET /documents?title=...` / `?author=...` (Phase 19) |

**Corpus document IDs (prod, live):**

| Document ID | Title | Status |
|---|---|---|
| `d_o3qBk5fESO_q` | Nurullayev & Papa 2023 | Ingested, hybrid search verified |
| `d_7ZUo22uPGdsf` | Kim 2023 | Ingested, hybrid search verified |
| `d_7lRaRsrtAJOW` | de Carvalho 2025 | Ingested, hybrid search verified |
| `d_ZikkNbPZFWWV` | Zeng 2026 | Ingested Session CA, verified Session 13 (list + scoped search, 10 chunks) |

Note: 4 dead document shells from Session 9's failed ingestion + 2 ArXiv test docs remain in prod DB — cleanup is the sibling repo's job.

---

## Recent Sessions

| Date | What was done |
|------|---------------|
| 2026-07-22 | Session 1: Fork, clone, PM setup, assessment artifact, websearch-and-costs doc |
| 2026-07-22 | Session 2: Flatten to agent-only, OpenRouter + tier-based registry, PDF ingest, /claimify skill, NLTK fix, OpenAI live test. 63 tests. |
| 2026-07-23 | Session 3: Reasoning effort fix, search cost tracking, config.toml extraction, OpenRouter live test, architecture audit. 87 tests. |
| 2026-07-23 | Session 4: Phase 02 plan written, first full academic paper PDF test (448 claims, $10 cost). |
| 2026-07-23 | Session 5: Phase 01 closed. Phase 02 approved. Standard dev test file established. |
| 2026-07-23 | Session 6: Phase 02 TGs 02.1–02.3 implemented. Data models, draft parsing, vault serializer. 195 tests. |
| 2026-07-23 | Session 7: Phase 02 TGs 02.4–02.6 implemented. Alignment, vault matching, gap report. Live spot-check. 245 tests. |
| 2026-07-24 | Session 8: Phase 02 CLOSED. Phase 03 implemented and milestone-accepted. 340 tests. |
| 2026-07-24 | Session 9: Phase 04 implemented. doc-rag-backend cloned, SSH, API key, ingestion initiated. 400 tests. |
| 2026-07-25 | Session 10: Phase 04 CLOSED. Phase 05 designed and approved. 403 tests. |
| 2026-07-25 | Session 11: Phase 05 TGs 05.1–05.4 implemented. Cascade routing, citation-aware scoping, D4/D5 cross-checks, conflict detection. Live milestone (cascade verified, source-conflict pending cited test file). 471 tests. |
| 2026-07-25 | Session 12: Phase 05 CLOSED. D10 support-confirmation amendment, alias-based note resolution, conflict-demo fixture, source-conflict demonstrated live. Cited-file corpus-scoping run. Cost doc updated. Exa credits exhausted (hard-cap confirmed). 488 tests. |
| 2026-07-25 | Session 13: Backlog maintenance — 4 fixes (zero-evidence verdicts, web-call counter, triage importance recalibration + core-data carve-out, Zeng 2026 corpus ID). 32 new tests, 523 total. Backlog clear for Phase 06. |
| 2026-07-25 | Session 14: Phase 06 prep — comparator set (5 claims × Exa/Tavily), integration surface mapping, evaluation metrics (speed/quality/cost), Fable + goal-loop orchestration approach. Exa confirmed dead (402 ×5). One new doc. |
| 2026-07-25 | Session 15: Phase 06 re-scoped and DEFERRED. Claude-native direction rejected (D60). Market scan (7 providers). PixSerp discovered, evaluated (32 live API calls across tiers/prompts). Query-design playbook written. crawl4ai service explored and documented. Cross-repo updates (control-hub IDEA note, web-interaction skill). No code changes. |
