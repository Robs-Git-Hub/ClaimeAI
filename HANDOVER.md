# Session Handover

**Last Updated:** 2026-07-25 (Session 12, outgoing)
**Current Status:** Phase 05 COMPLETE (closed Session 12). All milestone criteria met including live source-conflict demonstration. 488 tests. Next: Phase 06 planning or backlog items.

---

## Start Here

**Outgoing session completed:** Phase 05 CLOSED. Two design amendments (user-approved) plus the live source-conflict demonstration:

1. **D10 — support confirmation** (supersedes part of D5): vault/corpus-supported claims with importance ≥ 4 now get ONE independent web confirmation check. Rationale: a false fact shared by vault and draft previously passed with no independent check; user's verification-conservatism principle (missed errors are worst case) outweighed the Session 10 cost guardrail. User chose the ≥ 4 gate over the recommended ≥ 5, accepting ~2x web calls. Config switch: `support_confirmation` in config.toml (default true). Implemented in `_needs_support_confirm()` (`ingest/routing.py`), wired into `apply_cross_checks()`.
2. **Alias-based cited-note resolution**: `gather_evidence()` resolved wikilinks by filename stem only — `[[de Carvalho 2025]]` silently failed against `SOURCE-de-carvalho-2025-shifting-alliances.md`. Now `build_vault_index()` (`ingest/vault_serializer.py`) indexes notes by filename AND frontmatter `aliases` (filename wins; ambiguous aliases dropped — same conservatism as `map_citations_to_document_ids`). **Vault-side lint still needed** (sibling repo): every SOURCE note should carry an "Author Year" alias. Obsidian-authored links carry real filenames, so this is defense-in-depth for hand-written links.
3. **Source-conflict demonstrated live** (TG 05.5.2b): fixture at `tests/fixtures/conflict-demo/` — tiny committed vault with planted false tally ("140 votes in favour"; truth 141) + draft repeating the error. Run: vault_supported → D10 web confirmation → web Refuted (141) → `source-conflict` + REVISE-CLAIM in report. Command: `poetry run python scripts/run_heavy.py tests/fixtures/conflict-demo/draft.md --vault tests/fixtures/conflict-demo/vault-main --argument-pyramid conflict-demo`
4. **Cited-file milestone run**: `workspace/inbox/ukraine-intro-cited-test.md` (wikilinked variant of the standard test file) demonstrated citation-aware corpus scoping live: 16 claims, 8 vault / 4 corpus / 4 web, corpus→web cascade, ~2 min.
5. **Cost doc updated** (`docs/websearch-and-costs.md`): corpus profile (~$0.01–0.02/claim), D10 impact, Session 12 run data, Exa credit-cap correction, zero-evidence caveat.

**Incoming session should:**

1. **Decide next phase**: Phase 06 (Deep Research Commissions) planning, or backlog items first (see below).
2. **Exa is OUT OF CREDITS** (402 NO_MORE_CREDITS observed mid-session). Free tier = $20 sign-up + $10/month refresh (hard cap; rate limits are separate). config.toml committed default is `exa` (user decision) — flip to `tavily` locally for dev runs until Exa refreshes/topped up. Tavily verified working this session (1,000 free credits/month).
3. **High-value backlog items surfaced this session:**
   - Zero-evidence web verdicts return "Refuted" instead of insufficient (VerificationResult enum gap). A dead search provider silently produces refutations. Check search-error logs before trusting Refuted verdicts.
   - Gap report "Web calls made this run" counts routing decisions only — misses D4/D5/D10 cross-check calls (the conflict-demo report said "0 web calls" while making 9).
   - Vault aliases lint in sibling repo (see amendment 2 above).
   - Triage importance recalibration: importance clusters ≥ 4, so D10 fires on nearly all vault-resolved claims (9/9 in the demo run) — the gate barely gates. Recalibrating triage's importance guidance would restore cost control.
4. **Zeng 2026 ingestion** — check if doc-rag-backend has fixed the null-byte bug. If fixed, re-ingest and add document_id to corpus-ids.

**Critical config notes for heavy runs (unchanged):**
- `--vault` path must be the vault ROOT (`vault-main`), NOT `vault-main/v-research` — `load_vault()` appends `v-research` internally. Wrong path silently produces zero vault notes.
- `--argument-pyramid` value must be `un-ukraine-russia-war-votes-working-paper` for the real vault.
- Real-vault command: `poetry run python scripts/run_heavy.py workspace/inbox/ukraine-intro-cited-test.md --vault "PATH/vault-main" --argument-pyramid un-ukraine-russia-war-votes-working-paper --corpus-ids d_o3qBk5fESO_q,d_7ZUo22uPGdsf,d_7lRaRsrtAJOW`

**Phase plans:** `phase-02` through `phase-05` all COMPLETE. Phase 05 plan carries an "Amendment (Session 12)" section documenting D10.

---

## Current Context

### Repo structure

Agent packages at root: `claim_extractor/`, `claim_verifier/`, `fact_checker/`, `utils/`, `security/`, `scripts/`, `ingest/`. No `apps/` directory. `docs/playbook/` for decision rationale. Sibling repos: `../doc-rag-backend` (cloned Session 9), `../ukraine-vote-analysis` (vault + source PDFs).

### Configuration

**`config.toml`** — non-sensitive pipeline config. Sections: `[pipeline]` (llm_provider, search_provider, results_per_query, max_search_iterations, summarize_evidence, vault_match_fallback), `[models.*]` (tier->model mapping per provider), `[reasoning.*]` (reasoning effort per provider/tier), `[corpus_api]` (base_url, mode, top_k).

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

All present: `OPENAI_API_KEY` (sk-proj-, topped up Session 10), `EXA_API_KEY` (UUID, verified live), `OPENROUTER_API_KEY` (sk-or-v1, verified live), `TAVILY_API_KEY` (tvly-dev-, verified live), `REDIS_URI` + `REDIS_URL` (both redis://localhost:6379, Redis optional for local dev), `RAG_API_KEY` (64-char hex, provisioned Session 9, verified live).

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

### Test suite

491 tests total (488 pass with `-m "not slow"`, 3 slow tests). Session 12 added 20: 8 D10 (test_routing.py), 1 conflict-demo fixture guard (test_vault_serializer.py), 10 alias parsing/indexing (test_vault_serializer.py), 1 alias end-to-end (test_alignment.py).

| File | Count | Covers |
|------|-------|--------|
| test_models.py | 24 | MODEL_REGISTRY, tier resolution, provider routing, reasoning effort |
| test_settings.py | 18 | Pydantic settings, env var validation, RAG_API_KEY |
| test_ingest.py | 31 | PDF extraction, chunking, text dispatch, report rendering |
| test_cost_tracking.py | 12 | Search cost counter, estimates, free-tier balance, print_summary |
| test_config.py | 10 | TOML loading, sections, fallbacks, real config.toml validation, corpus_api section |
| test_claim_record.py | 28 | ClaimRecord, enums incl. CorpusVerdict, conflict_flags, DraftPosition, RouteVerdict, serialization |
| test_run_config.py | 24 | ResourceManifest, RunProfile, available_routes incl. corpus, vault-less degradation |
| test_draft_parser.py | 25 | Wikilink parsing, stripping, author-year detection, sentence splitting, ParsedDraft |
| test_citation_binder.py | 15 | Citation binding via original_index, union semantics, decomposition survival |
| test_vault_serializer.py | 24 | Vault note parsing, filtering, serialization, token counting (22 narrow + 2 slow) |
| test_alignment.py | 22 | gather_evidence (8), evaluate_alignment (12 + 2 fallback) |
| test_vault_match.py | 42 | batch_match_claims, verify_matches, fallback, supersede, keywords, contradiction |
| test_gap_report.py | 33 | assign_suggested_actions, render_gap_report, serialize_results, detect_conflicts, source-conflict rendering, single-lineage annotation |
| test_triage.py | 13 | Batch triage, conservative fallback, importance clamping, prompt content |
| test_routing.py | 72 | Policy rows, cascade (normalize_verdict, execute_routing multi-round), D4/D5 cross-checks, extensibility proof |
| test_evidence_summarization.py | 11 | On/off switch, extract mapping, refuting content, fallback paths |
| test_corpus_client.py | 22 | Search request/response, pagination, citation mapping, degradation |
| test_corpus_route.py | 23 | Handler verdicts, provenance, factory wiring, citation-aware scoping, manifest gating |
| test_orchestration.py | 25 | Pipeline composition, no-vault degrade, corpus wiring with documents, CLI parsing, cross-checks wiring |
| test_ingest.py (slow) | 1 | Docling PDF extraction (~16s) |

### Phase 05 new/modified files (Session 11)

| File | Changes |
|------|---------|
| `ingest/routing.py` | +306 lines: `normalize_verdict()`, `_is_cascade_silent()`, cascade in `execute_routing()`, `_redecide()`, `apply_cross_checks()` with `_needs_d4()`/`_needs_d5()` |
| `ingest/corpus_route.py` | +89 lines: `documents` param on factory, `_resolve_search_scope()`, `corpus_cited_doc` provenance type |
| `ingest/gap_report.py` | +172 lines: `detect_conflicts()`, `_opposing()`, `_is_single_lineage()`, `_render_source_conflict()`, vault-corpus mismatch section |
| `utils/claim_record.py` | +9 lines: `conflict_flags: List[str]` field |
| `scripts/run_heavy.py` | +25 lines: `list_documents()` pre-fetch, `apply_cross_checks()` wiring, `detect_conflicts()` wiring |
| `docs/playbook/claim-record-design.md` | Phase 05 section: normalization table, lineage groups, conflict flags, cross-check gates |
| `CLAUDE.md` | Pipeline section rewritten for cascade |

### Hetzner / doc-rag-backend state (Session 9, unchanged)

| Item | Status |
|------|--------|
| Server | `ubuntu-8gb-hel1-1`, healthy, SSH on port 49152 |
| Compose dir | `/home/app/doc-rag-backend/code/` |
| App container | `code-app-1`, healthy |
| Supabase prod | `prod-ragtogo` (ref `rmxgiszgfycfwlfurdvu`) |
| Pinecone prod | `doc-rag-prod` (1536 dims, serverless) |
| DOC_RAG_API_KEY | Provisioned Session 9 (64-char hex) |
| Ingestion | 3 of 4 papers ingested; Zeng 2026 blocked by null-byte bug |

**Corpus document IDs (prod, live):**

| Document ID | Title | Status |
|---|---|---|
| `d_o3qBk5fESO_q` | Nurullayev & Papa 2023 | Ingested, hybrid search verified |
| `d_7ZUo22uPGdsf` | Kim 2023 | Ingested, hybrid search verified |
| `d_7lRaRsrtAJOW` | de Carvalho 2025 | Ingested, hybrid search verified |
| -- | Zeng 2026 | Blocked (null-byte bug in backend) |

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
