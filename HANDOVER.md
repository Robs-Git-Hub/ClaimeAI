# Session Handover

**Last Updated:** 2026-07-25 (Session 11, outgoing)
**Current Status:** Phase 05 TGs 05.1–05.4 COMPLETE (implementation + tests). TG 05.5 milestone PARTIAL — cascade demonstrated live, source-conflict flag not demonstrated (needs cited test file).

---

## Start Here

**Outgoing session completed:** Phase 05 implementation (68 new tests, 471 total). Three-tier evidence cascade (vault→corpus→web) fully operational: `normalize_verdict()`, cascade in `execute_routing()`, citation-aware corpus scoping, D4/D5 importance-gated cross-checks, pure-code conflict detection with `source-conflict` and `vault-corpus-check-needed` flags, single-lineage annotations in gap report. Live milestone run: 17 claims, 11 vault-resolved, 5 corpus, 1 web, ~2 min. Source-conflict flag tested offline (13 tests) but not demonstrated live — requires a cited test file whose wikilinks map to corpus documents.

**Incoming session should:**

1. **Create a cited test file** for source-conflict demonstration. Add wikilink citations to `ukraine-intro-test.txt` (or create a new file) — e.g., the "98 votes" sentence needs `[[de Carvalho 2025]]` so D4 fires. The citation must map to corpus document `d_7lRaRsrtAJOW` via `map_citations_to_document_ids()`. Then re-run the milestone and verify `source-conflict` appears in the report.

2. **Critical config notes for milestone run:**
   - `--vault` path must be the vault ROOT (`vault-main`), NOT `vault-main/v-research` — `load_vault()` appends `v-research` internally. Wrong path silently produces zero vault notes.
   - `--argument-pyramid` value must be `un-ukraine-russia-war-votes-working-paper` (changed from `ukraine-vote` in the sibling vault repo).
   - Working command: `poetry run python scripts/run_heavy.py workspace/inbox/ukraine-intro-test.txt --vault "PATH/vault-main" --argument-pyramid un-ukraine-russia-war-votes-working-paper --corpus-ids d_o3qBk5fESO_q,d_7ZUo22uPGdsf,d_7lRaRsrtAJOW`

3. **Update `docs/websearch-and-costs.md`** with corpus cost profile (~$0.01–0.02/claim: self-hosted search ~$0, mid summarize + high evaluate). Record Session 11 milestone run cost and wall-clock.

4. **Decide whether Phase 05 closes** on cited-test-file demonstration or on infrastructure evidence (471 tests, cascade live-verified, conflict mechanism unit-tested). If closing, update TASKS.md and HANDOVER.md, push to origin.

5. **Zeng 2026 ingestion** — check if doc-rag-backend has fixed the null-byte bug. If fixed, re-ingest and add document_id to corpus-ids.

**What was NOT done:**
- **Source-conflict live demonstration** — mechanism implemented and tested, but no test file triggers D4 (citation-aware corpus check alongside vault). Needs a wikilinked test file.
- **`docs/websearch-and-costs.md`** — corpus cost profile not added.
- **Light-profile regression** — not run end-to-end (offline tests cover it; 471 pass).

**Phase plans:** `phase-02-vault-verification-core.md` (COMPLETE), `phase-03-triage-and-routing.md` (COMPLETE), `phase-04-corpus-rag-route.md` (COMPLETE), `phase-05-three-tier-evidence-cascade.md` (IMPLEMENTATION COMPLETE, MILESTONE PARTIAL)

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

### Key decisions made

1–50: See Session 10 handover (preserved in git history).
51. **Vault `argument_pyramid` tag renamed** (Session 11 discovery). Vault notes changed from `ukraine-vote` to `un-ukraine-russia-war-votes-working-paper`. CLI `--argument-pyramid` must match current vault frontmatter exactly — mismatch silently loads zero notes.
52. **`load_vault()` path convention** (Session 11 discovery). Pass the vault ROOT (e.g. `vault-main`), not the research subdirectory. The function appends `v-research` internally. Wrong path silently produces zero vault notes (no error raised).
53. **Source-conflict requires cited claims** (Session 11 finding). D4 attribution check (the only path to both corpus and web verdicts on the same claim) requires `citation_status == CITED`. Citation-free test files can demonstrate the cascade but not the conflict flags.

### Test suite

471 tests total (468 pass with `-m "not slow"`, 3 slow tests).

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
