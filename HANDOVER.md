# Session Handover

**Last Updated:** 2026-07-24 (Session 9, outgoing)
**Current Status:** Phase 02 COMPLETE. Phase 03 COMPLETE. Phase 04 (Corpus RAG Route) IN PROGRESS — all offline implementation done, milestone blocked on ingestion confirmation.

---

## Start Here

**Outgoing session completed:** Phase 04 planned (Fable orchestration with 3 Haiku explore agents + doc-rag-backend clone), approved, and TGs 04.1–04.4.1 implemented in one session. All offline code is done and MID-green (400 tests). SSH access to Hetzner established, fresh `DOC_RAG_API_KEY` provisioned and deployed, Supabase prod DB unpaused, 4 clean ukraine-paper PDFs uploaded and ingestion via `POST /documents` initiated at session end. Cross-repo client-needs note committed to doc-rag-backend dev branch.

**Incoming session should:**

1. **Re-ingest the 4 papers.** The outgoing session's ingestion calls all failed: the backend's OpenAI API key (used for `text-embedding-3-small` embeddings) is **out of quota** — same issue ClaimeAI hit in Session 5. Document rows were created (IDs below) but all pipeline stages are `None` (no parse, no chunks, no embeddings). The PDFs remain on the server at `/data/pdfs/` inside the container.

   | Document ID | Title |
   |---|---|
   | `d_OOfQK0u0hSFA` | Nurullayev & Papa 2023 |
   | `d_2IBOCexW_qQY` | Kim 2023 |
   | `d_wERrWO7aNPBt` | Zeng 2026 |
   | `d_MWigEjhYX4xO` | de Carvalho 2025 |

   **To unblock:** either (a) top up the backend's OpenAI account, or (b) SSH to Hetzner and switch the backend's embedding model to OpenRouter in its env config (the backend already supports OpenRouter for enrichment LLM calls — check if it also supports OpenRouter for embeddings, or if embedding is hardcoded to OpenAI). Then either delete the failed document rows and re-POST, or check if the backend supports re-running failed pipeline stages (look at the orchestrator code). The PDFs don't need re-uploading.

2. **Verify search works** once ingestion succeeds. Test a scoped search:
   ```bash
   KEY=$(grep '^RAG_API_KEY=' .env | cut -d= -f2) && curl -s -H "X-API-Key: $KEY" "https://api.ragtogo.com/search?q=UN+voting+patterns&document_ids=<comma-sep-ids>&top_k=5"
   ```
   Check `search_mode` in the response (`"hybrid"` = Pinecone working, `"fts_fallback"` = FTS only).

3. **Run the milestone (TG 04.4.2).** All offline code is done. The CLI is:
   ```bash
   LLM_PROVIDER=openrouter poetry run python scripts/run_heavy.py workspace/inbox/ukraine-intro-test.txt --vault ../ukraine-vote-analysis/vault-main --argument-pyramid un-ukraine-russia-war-votes-working-paper --corpus-ids <comma-sep-ids>
   ```
   Success: the 3 dataset-dependent claims receive corpus verdicts with document-id provenance (or honest `corpus_insufficient` with reasoning). User judges the report useful. Record wall-clock and cost.

4. **Wrap Phase 04 (TG 04.5)** if the milestone passes: `docs-align-check`, update `docs/websearch-and-costs.md` with corpus cost profile (near-zero marginal search cost — self-hosted), update HANDOVER, push to origin.

**What was NOT done (deferred quality gates):**
- **TG 04.4.2 milestone** — not executed. All code is implemented and MID-tested but the live corpus-scoped heavy run did not happen. Reason: paper ingestion failed — backend's OpenAI key is out of quota (embedding stage). Document rows created but empty (all stages None). PDFs are on the server; re-ingestion needed once API key issue resolved.
- **TG 04.5 docs-align-check** — not run (depends on milestone).
- **`docs/websearch-and-costs.md`** — not updated with corpus cost profile.
- **Pinecone vector sync verification** — embeddings rows are written by the ingestion pipeline but Pinecone sync status (`sync_status` in `tbl_embeddings`) was not checked. If all `sync_status = "synced"`, hybrid search works. If `"pending"`, search runs FTS-only fallback.
- **Light-profile regression** — not run end-to-end via `run_from_pdf.py` (offline test `test_report_no_vault_section_when_no_vault` covers it, but no live run this session).

**Phase plans:** `phase-02-vault-verification-core.md` (COMPLETE), `phase-03-triage-and-routing.md` (COMPLETE), `phase-04-corpus-rag-route.md` (IN PROGRESS — TGs 04.1–04.4.1 done, 04.4.2 + 04.5 remain)

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

All present: `OPENAI_API_KEY` (sk-proj-, **OUT OF CREDIT as of Session 5**), `EXA_API_KEY` (UUID, verified live), `OPENROUTER_API_KEY` (sk-or-v1, verified live), `TAVILY_API_KEY` (tvly-dev-, verified live), `REDIS_URI` + `REDIS_URL` (both redis://localhost:6379, Redis optional for local dev), `RAG_API_KEY` (64-char hex, provisioned Session 9, verified live against api.ragtogo.com — `GET /documents` returned 200).

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
| Session 7 | OpenRouter | — | Vault alignment + matching spot-check: 3 vault_supported, 9 vault_supported (matching), 4 note_not_in_vault. 13 API calls. |
| Session 8 run 1 | OpenRouter | Exa | Phase 03 milestone (pre-triage-fix): 15 claims, 3 web / 12 unverifiable. |
| Session 8 run 2 | OpenRouter | Exa | Post-triage-fix: 15 claims, 14 web / 1 trivial. "98 votes" Refuted by web. |
| Session 8 run 3 | OpenRouter | Exa | Post-parallelization: 11 claims (extraction variance), ~4 min. |
| Session 8 run 4 (final) | OpenRouter | Exa | 15 claims, 8 vault-resolved / 7 web. "98 votes" caught by vault. ~4 min. |
| Session 9 | — | — | api.ragtogo.com: `/health` verified (healthy), `/documents` authenticated (200). 4 PDFs uploaded + ingestion FAILED (backend OpenAI key out of quota at embedding stage). Doc rows created, all stages None. |

### Key decisions made

1–40: See Session 8 handover (preserved in git history).
41. **Phase 04 plan approved** (Session 9). Prod-first, cross-repo commits approved, find-or-generate API key authorized.
42. **Router extensibility validated by second real route** (Session 9). Gap report, execute_routing, ClaimRecord untouched — pillar 3 confirmed. Design finding: `VerificationResult` enum in claim_verifier can't express richer verdict vocabularies (e.g. `corpus_insufficient`), so routes with richer vocabularies use route-local evaluation (following `ingest/alignment.py` pattern).
43. **Corpus handler uses factory pattern** (Session 9). `make_corpus_route_handler(corpus_ids)` solves the manifest-scoping problem without changing `RouteHandler` protocol or `execute_routing` signature.
44. **Corpus route only for never-web claims this phase** (Session 9). Deliberate scope line — web-eligible rows (general-factual, academic-citable, unclassified) continue to route to web. Documented in claim-record-design.md.
45. **Eval-seed papers are dirty test copies** (Session 9 user correction). Clean originals ingested from ukraine-vote-analysis repo + Zotero storage instead.
46. **SSH access established from this Windows machine** (Session 9). ed25519 key at `~/.ssh/id_ed25519`, authorized via Hetzner console. `clip.exe` piping for long one-liners.
47. **Fresh DOC_RAG_API_KEY provisioned** (Session 9). 64-char hex generated, set in `/home/app/doc-rag-backend/code/.env.production.local`, container recreated. Stored as `RAG_API_KEY` in ClaimeAI `.env`.

### Test suite

400 tests total (397 pass with `-m "not slow"`, 3 slow tests deselected).

| File | Count | Covers |
|------|-------|--------|
| test_models.py | 24 | MODEL_REGISTRY, tier resolution, provider routing, reasoning effort |
| test_settings.py | 18 | Pydantic settings, env var validation, RAG_API_KEY |
| test_ingest.py | 31 | PDF extraction, chunking, text dispatch, report rendering |
| test_cost_tracking.py | 12 | Search cost counter, estimates, free-tier balance, print_summary |
| test_config.py | 10 | TOML loading, sections, fallbacks, real config.toml validation, corpus_api section |
| test_claim_record.py | 31 | ClaimRecord, enums incl. CorpusVerdict, DraftPosition, RouteVerdict, serialization |
| test_run_config.py | 24 | ResourceManifest, RunProfile, available_routes incl. corpus, vault-less degradation |
| test_draft_parser.py | 25 | Wikilink parsing, stripping, author-year detection, sentence splitting, ParsedDraft |
| test_citation_binder.py | 15 | Citation binding via original_index, union semantics, decomposition survival |
| test_vault_serializer.py | 24 | Vault note parsing, filtering, serialization, token counting (22 narrow + 2 slow) |
| test_alignment.py | 22 | gather_evidence (8), evaluate_alignment (12 + 2 fallback) |
| test_vault_match.py | 42 | batch_match_claims, verify_matches, fallback, supersede, keywords, contradiction |
| test_gap_report.py | 18 | assign_suggested_actions, render_gap_report, serialize_results, route summary |
| test_triage.py | 13 | Batch triage, conservative fallback, importance clamping, prompt content |
| test_routing.py | 28 | Policy rows, extensibility proof, web handler, execute_routing, routing reasons |
| test_evidence_summarization.py | 19 | On/off switch, extract mapping, refuting content, fallback paths |
| test_corpus_client.py | 22 | Search request/response, pagination, citation mapping, degradation |
| test_corpus_route.py | 15 | Handler verdicts, provenance, factory wiring, manifest gating, tier assertion |
| test_orchestration.py | 23 | Pipeline composition, no-vault degrade, corpus wiring, CLI parsing |
| test_ingest.py (slow) | 1 | Docling PDF extraction (~16s) |

### Phase 04 new files (Session 9)

| File | Purpose |
|------|---------|
| `ingest/corpus_client.py` | HTTP client: search_corpus(), list_documents(), map_citations_to_document_ids() |
| `ingest/corpus_route.py` | Route handler: make_corpus_route_handler(corpus_ids) factory, route-local high-tier evaluation |
| `tests/test_corpus_client.py` | Corpus client offline tests (httpx.MockTransport) |
| `tests/test_corpus_route.py` | Corpus route handler tests (mocked LLM + client) |
| `project-management/phase-plans/phase-04-corpus-rag-route.md` | Phase 04 plan |

### Hetzner / doc-rag-backend state (Session 9)

| Item | Status |
|------|--------|
| Server | `ubuntu-8gb-hel1-1`, healthy, SSH on port 49152 |
| Compose dir | `/home/app/doc-rag-backend/code/` (NOT `/opt/doc-rag-backend` — HANDOVER was stale) |
| App container | `code-app-1`, healthy |
| Supabase prod | `prod-ragtogo` (ref `rmxgiszgfycfwlfurdvu`), was paused (auto-pause), unpaused Session 9 |
| Pinecone prod | `doc-rag-prod` (1536 dims, serverless) |
| DOC_RAG_API_KEY | Provisioned and deployed Session 9 (64-char hex in `.env.production.local`) |
| PDFs uploaded | 4 files at `/home/app/doc-rag-backend/code/pdfs/` (mapped to `/data/pdfs/` in container) |
| Ingestion | Initiated via POST /documents at session end — **completion unconfirmed** |
| Backend repo | Cloned at `../doc-rag-backend`; client-needs note committed to origin/dev (463c155) |

---

## Recent Sessions

| Date | What was done |
|------|---------------|
| 2026-07-22 | Session 1: Fork, clone, PM setup, assessment artifact, websearch-and-costs doc |
| 2026-07-22 | Session 2: Flatten to agent-only, OpenRouter + tier-based registry, PDF ingest (Docling), /claimify skill, NLTK fix, OpenAI live test, tier rebalancing, model selection playbook, Sonnet 5 hybrid-reasoning correction. 63 tests. 13 commits. |
| 2026-07-23 | Session 3: Reasoning effort fix, search cost tracking, dead export cleanup, config.toml extraction, OpenRouter live test, Exa vs Tavily comparison, architecture audit. 87 tests. 7 commits. |
| 2026-07-23 | Session 4: Emoji fix in dev.py, design discussion on academic verification scope, Phase 02 plan written, first full academic paper PDF test (448 claims, $10 cost with analysis). |
| 2026-07-23 | Session 5: Phase 01 closed. Phase 02 approved. Standard dev test file established. Vault corrections: 98->93 across 9 notes. 4 commits. |
| 2026-07-23 | Session 6: Phase 02 TGs 02.1–02.3 implemented. Data models, draft parsing + citation binding, vault serializer. 107 new tests (195 total). |
| 2026-07-23 | Session 7: Phase 02 TGs 02.4–02.6 implemented. Cited-claim alignment, citation-free vault matching, gap report. Live spot-check passed. 50 new tests (245 total). 3 commits. |
| 2026-07-24 | Session 8: Phase 02 CLOSED. Phase 03 planned, implemented, milestone-accepted. TGs 03.1–03.6. ~95 new tests (340 total). |
| 2026-07-24 | Session 9: Phase 04 planned (Fable + 3 Haiku explorers), approved, and TGs 04.1–04.4.1 implemented. doc-rag-backend cloned, SSH established, API key provisioned, Supabase unpaused, 4 clean PDFs uploaded + ingestion initiated. Cross-repo client-needs note. 60 new tests (400 total). Milestone deferred to incoming session (ingestion completion unconfirmed). |
