# Session Handover

**Last Updated:** 2026-07-24 (Session 8, outgoing)
**Current Status:** Phase 02 COMPLETE. Phase 03 COMPLETE. Phase 04 (Corpus RAG Route) ready for planning.

---

## Start Here

**Outgoing session completed:** Phase 02 closed (milestone accepted via spot-check). Phase 03 (Triage & Routing) planned, implemented, and milestone-accepted in a single session — 6 task groups, ~95 new tests (340 total), 4 live milestone runs. Final run: 15 claims, 8 vault-resolved (including the "98 votes" error caught as vault_contradicted with 4 provenance notes), 7 web-checked, ~4 min wall-clock.

**Incoming session should:**

1. **Begin Phase 04 planning** (Corpus RAG Route). The full first-client directive is in the Phase 03 plan's roadmap section AND in memory (`project_doc_rag_backend_first_client.md`): we own both repos, sole users; approach api.ragtogo.com as its first genuine client; record client needs (DB visibility, search by author+title/DOI/Zotero ref, API help); improvements via direct edit + redeploy to Hetzner or cross-repo communication note. Backend facts: live on Hetzner, likely test + prod DBs, some ukraine sources probably ingested (unconfirmed). No doc-rag-backend sibling repo is checked out locally — clone it first.

2. **Optionally run the full paper** through the heavy pipeline to validate at scale (~450 claims). The scale behavior (batch matching context window, parallelization under load) was never tested. CLI: `LLM_PROVIDER=openrouter poetry run python scripts/run_heavy.py <draft-path> --vault ../ukraine-vote-analysis/vault-main --argument-pyramid un-ukraine-russia-war-votes-working-paper`. Costs API credit.

3. **Optionally run `ukraine-rich-wikilinks-test.md`** through `run_heavy.py` to exercise the cited-claim alignment path through the production wiring (it was only proven via `spot_check_vault.py` in Phase 02).

**What was NOT done:**
- Light-profile regression test via live run (covered by offline tests: `test_report_no_vault_section_when_no_vault`, but not exercised end-to-end through `run_heavy.py` or `run_from_pdf.py`).
- Verdict A/B spot-check for evidence summarization (summarization on vs off on the same claims). The three Refuted verdicts survived summarization across multiple runs, but a controlled comparison was not performed.
- The `suggested_action` logic (`assign_suggested_actions`) is Phase 02 code, unchanged — it doesn't know about triage classes. A citation-free novel-result claim with no vault match still gets `ADD_CITATION`, which is odd for the author's own results. The honest story is in `routing_decision = unverifiable-by-available-routes`. Worth a triage-aware action pass if the user wants it.

**Phase plans:** `phase-02-vault-verification-core.md` (COMPLETE), `phase-03-triage-and-routing.md` (COMPLETE)

---

## Current Context

### Repo structure

Agent packages at root: `claim_extractor/`, `claim_verifier/`, `fact_checker/`, `utils/`, `security/`, `scripts/`, `ingest/`. No `apps/` directory. `docs/playbook/` for decision rationale.

### Configuration

**`config.toml`** — non-sensitive pipeline config. Sections: `[pipeline]` (llm_provider, search_provider, results_per_query, max_search_iterations, summarize_evidence, vault_match_fallback), `[models.*]` (tier->model mapping per provider), `[reasoning.*]` (reasoning effort per provider/tier). Environment variables override config.toml values via Pydantic.

**`.env`** — secrets only: `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `EXA_API_KEY`, `TAVILY_API_KEY`, `REDIS_URI`/`REDIS_URL`.

### Environment

| Component | Detail |
|-----------|--------|
| Python | 3.11.15 via uv |
| Poetry | 2.4.1 via `uv tool install poetry` |
| Venv | `C:\vpy\claime-agent-j1KWVyi4-py3.11` |
| Dev server | `poetry run dev` (light profile only) |
| Heavy runs | `poetry run python scripts/run_heavy.py` (in-process, no dev server needed) |

### API keys configured (.env at repo root)

All present: `OPENAI_API_KEY` (sk-proj-, **OUT OF CREDIT as of Session 5**), `EXA_API_KEY` (UUID, verified live), `OPENROUTER_API_KEY` (sk-or-v1, verified live), `TAVILY_API_KEY` (tvly-dev-, verified live), `REDIS_URI` + `REDIS_URL` (both redis://localhost:6379, Redis optional for local dev).

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
| Session 8 run 1 | OpenRouter | Exa | Phase 03 milestone (pre-triage-fix): 15 claims, 3 web / 12 unverifiable. "98 votes" error missed (misclassified as dataset-dependent). |
| Session 8 run 2 | OpenRouter | Exa | Post-triage-fix: 15 claims, 14 web / 1 trivial. "98 votes" Refuted by web. Evidence summarization: 60–83% reduction. |
| Session 8 run 3 | OpenRouter | Exa | Post-parallelization: 11 claims (extraction variance), ~4 min. |
| Session 8 run 4 (final) | OpenRouter | Exa | Post high-tier fallback + contradiction prompt: 15 claims, 8 vault-resolved / 7 web. "98 votes" caught by vault (4× vault_contradicted, provenance: QUOTE-de-carvalho-2022-2024-consensus, SOURCE-unga-res-es-11-7, QUOTE-de-carvalho-national-interests). 19 tag-gap signals. ~4 min. |

### Key decisions made

1–28: See Session 7 handover (preserved in git history).
29. **Phase 02 milestone accepted via spot-check** (Session 8).
30. **Corpus RAG split out to Phase 04** (Session 8). Router is an extension point.
31. **Web route is triage-gated** (Session 8). Trivial and novel-result/dataset-dependent claims never hit web.
32. **First-client principle for doc-rag-backend** (Session 8). Full directive in Phase 04 roadmap.
33. **Phase 03 milestone = standard test file** (Session 8).
34. **Evidence summarization added to Phase 03** (Session 8 amendment). Mid-tier condenses raw evidence before high-tier evaluation. Config-switchable (summarize_evidence, default on). Reusable for Phase 04 corpus passages.
35. **Triage prompt tightened after milestone failure** (Session 8). dataset-dependent = author's own private data ONLY, not public records. Directional tie-break: uncertain between never-web and web-verifiable → choose web-verifiable. User principle: "better to send too much to web than too little; a missed error is the worst case."
36. **Full-vault fallback promoted to high tier** (Session 8). One batch call per run, all unmatched claims. User decision: "we can afford to do it once at high tier."
37. **Contradiction-seeking batch-match prompt** (Session 8). "A note with a different number for the same fact is a match." Plus keyword pre-filter surfacing priority candidates from vault.
38. **Pipeline parallelization** (Session 8). Voting across sentences, web verification across claims, vault verify across proposals — all concurrent with semaphore(5). 3.4x speedup.
39. **`vault_verdicts` renamed to `route_verdicts`** (Session 8). Generic field name; pre-release internal API, no external consumers.
40. **Record identity via `ClaimRecord.claim`** (Session 8). ValidatedClaim populated from extraction, independent of web_verdict. No fake web results fabricated.

### Test suite

340 tests total (337 pass with `-m "not slow"`, 3 slow tests deselected).

| File | Count | Covers |
|------|-------|--------|
| test_models.py | 24 | MODEL_REGISTRY, tier resolution, provider routing, reasoning effort |
| test_settings.py | 13 | Pydantic settings, env var validation |
| test_ingest.py | 31 | PDF extraction, chunking, text dispatch, report rendering |
| test_cost_tracking.py | 12 | Search cost counter, estimates, free-tier balance, print_summary |
| test_config.py | 9 | TOML loading, sections, fallbacks, real config.toml validation, summarize_evidence knob |
| test_claim_record.py | 28 | ClaimRecord, enums, DraftPosition, RouteVerdict, routing fields, serialization |
| test_run_config.py | 20 | ResourceManifest, RunProfile, available_routes, vault-less degradation |
| test_draft_parser.py | 25 | Wikilink parsing, stripping, author-year detection, sentence splitting, ParsedDraft |
| test_citation_binder.py | 15 | Citation binding via original_index, union semantics, decomposition survival |
| test_vault_serializer.py | 24 | Vault note parsing, filtering, serialization, token counting (22 narrow + 2 slow live vault) |
| test_alignment.py | 22 | gather_evidence (8), evaluate_alignment (12 + 2 fallback, async with mocked LLM) |
| test_vault_match.py | 42 | batch_match_claims, verify_matches, fallback, supersede, keywords, contradiction prompt, tier promotion |
| test_gap_report.py | 18 | assign_suggested_actions, render_gap_report, serialize_results, route summary, unparsed count, tag-gap signals |
| test_triage.py | 13 | Batch triage, conservative fallback, importance clamping, prompt content assertions |
| test_routing.py | 28 | Policy rows, extensibility proof, web handler, execute_routing, routing reasons |
| test_evidence_summarization.py | 19 | On/off switch, extract mapping, refuting content, fallback paths, integration with evaluate_evidence |
| test_orchestration.py | 8 | End-to-end pipeline composition, no-vault degrade, extraction failure, fallback wiring |
| test_ingest.py (slow) | 1 | Docling PDF extraction (~16s) |

### Phase 03 new files (Session 8)

| File | Purpose |
|------|---------|
| `ingest/triage.py` | Batch triage: triage_claims(), TriageProposal, BatchTriageOutput |
| `ingest/routing.py` | Routing: POLICY table, decide_route(), execute_routing(), web_route_handler(), route registry |
| `claim_verifier/evidence_summarization.py` | Reusable summarize_evidence_for_claim() + prompts |
| `scripts/run_heavy.py` | Production heavy-pipeline CLI entry point |
| `tests/test_triage.py` | Triage offline tests |
| `tests/test_routing.py` | Routing policy + handler tests |
| `tests/test_evidence_summarization.py` | Summarization on/off, safety, fallback tests |
| `tests/test_orchestration.py` | End-to-end pipeline composition tests |

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
| 2026-07-24 | Session 8: Phase 02 CLOSED. Phase 03 planned (Fable orchestration with 3 Haiku explore agents), restructured (corpus RAG → Phase 04), approved, and fully implemented in one session. TGs 03.1–03.5: triage classifier, routing policy + registry, production orchestration (run_heavy.py), evidence summarization, pipeline parallelization. Iterative milestone runs: triage prompt tightened after "98 votes" miss, full-vault fallback promoted to high tier, contradiction-seeking prompt + keyword pre-filter added. Final run: 15 claims, 8 vault-resolved, "98 votes" caught with 4 vault_contradicted provenance notes, ~4 min. ~95 new tests (340 total). |
