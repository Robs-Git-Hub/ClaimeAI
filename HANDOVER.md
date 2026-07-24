# Session Handover

**Last Updated:** 2026-07-24 (Session 8, outgoing)
**Current Status:** Phase 02 COMPLETE. Phase 03 (Triage & Routing) APPROVED — ready for implementation.

---

## Start Here

**Outgoing session completed:** Phase 02 closed (milestone accepted via spot-check — user judged the full-paper run unnecessary; `docs-align-check` ran clean: 46 paths verified, test counts match, zero drift). Phase 03 planned, restructured after user design review, and approved.

**Incoming session should:**

1. **Read the Phase 03 plan first:** `project-management/phase-plans/phase-03-triage-and-routing.md`. Four TGs: 03.1 triage classifier (batch, mid tier or below, conservative-up), 03.2 routing policy + route registry (pure function, route-handler interface, extensibility proof test), 03.3 orchestration + report extension (production heavy-run entry point — pays down the spot-check-script integration debt), 03.4 quality & wrap.

2. **Start with TG 03.1 and/or 03.2** — they are independent (03.1 is LLM vocabulary + batch classification; 03.2 is pure-code routing). Task breakdown within TGs is the implementing session's job.

3. **Two user-review gates before the milestone:** the routing table (which triage class × citation status → which route) must be reviewed by the user before the milestone run (TG 03.2 constraint); the milestone report itself is the acceptance gate (TG 03.4).

4. **Milestone is the standard test file only** (`workspace/inbox/ukraine-intro-test.txt`) — success = the 3 dataset-dependent claims route away from web. Full-paper runs are post-phase optional, user-triggered.

**Scope boundaries (user decisions, Session 8 — do not re-litigate):**
- **Corpus RAG (doc-rag-backend) is Phase 04, not Phase 03.** Phase 03 must make the router extensible (routes additive via registry + policy table), validated by a fake-route test. The Phase 04 roadmap entry in the phase plan carries the full first-client directive for api.ragtogo.com — read it before planning Phase 04.
- **Web is triage-gated.** Trivial and novel-result/dataset-dependent claims never hit web search.
- **Vault QA** (verifying vault notes against original sources) stays on the backlog — separate domain from draft-claim verification.

**Phase plans:** `phase-02-vault-verification-core.md` (COMPLETE), `phase-03-triage-and-routing.md` (APPROVED)

---

## Current Context

### Repo structure (post-flatten)

Agent packages at root: `claim_extractor/`, `claim_verifier/`, `fact_checker/`, `utils/`, `security/`, `scripts/`, `ingest/`. No `apps/` directory. `docs/playbook/` for decision rationale.

### Configuration

**`config.toml`** — non-sensitive pipeline config. Sections: `[pipeline]` (llm_provider, search_provider, results_per_query, max_search_iterations), `[models.*]` (tier->model mapping per provider), `[reasoning.*]` (reasoning effort per provider/tier). Environment variables override config.toml values via Pydantic.

**`.env`** — secrets only: `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `EXA_API_KEY`, `TAVILY_API_KEY`, `REDIS_URI`/`REDIS_URL`.

### Environment

| Component | Detail |
|-----------|--------|
| Python | 3.11.15 via uv (`~\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe`) |
| Poetry | 2.4.1 via `uv tool install poetry` |
| Venv | `C:\vpy\claime-agent-j1KWVyi4-py3.11` (short path for Windows MAX_PATH) |
| langgraph-cli | 0.4.8 / langgraph-api 0.4.48 (EOL — upgrade available to 0.11.x, not urgent) |
| Docling models | Cached in `~/.cache/huggingface/` (~505 MB) |
| Dev server | `poetry run dev` or `poetry run langgraph dev --no-browser --allow-blocking` |

### API keys configured (.env at repo root)

All present: `OPENAI_API_KEY` (sk-proj-, **OUT OF CREDIT as of Session 5** — top up before OpenAI-provider runs), `EXA_API_KEY` (UUID, verified live), `OPENROUTER_API_KEY` (sk-or-v1, verified live), `TAVILY_API_KEY` (tvly-dev-, verified live), `REDIS_URI` + `REDIS_URL` (both redis://localhost:6379, Redis optional for local dev).

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
| Session 5 | OpenAI | Exa | FAILED (429 insufficient_quota) — error recorded cleanly |
| Session 5 | OpenRouter | Exa | 15 claims (ukraine-intro-test.txt), 10 supported / 5 refuted |
| Session 7 | OpenRouter | — | Vault alignment + matching spot-check: 3 vault_supported (alignment), 9 vault_supported (matching), 4 note_not_in_vault (correct filtering). 13 API calls. |

### Key decisions made

1–23: See Session 6 handover (preserved in git history).
24. **Any wikilink type is a citation target** (Session 7, user correction). The phase plan originally assumed only SOURCE→QUOTE chains. The real draft cites DESIGN, RESULT, CLAIM, HYP notes — all levels of the argument pyramid. The alignment evaluator resolves ANY cited note + one-hop linked notes as evidence.
25. **One-hop traversal for evidence gathering** (Session 7, user decision). For each cited note, gather the note's own body content PLUS the content of notes it directly links to (one hop). Deeper traversal has diminishing returns and token cost.
26. **VaultVerdict renamed: SOURCE_NOT_IN_VAULT → NOTE_NOT_IN_VAULT** (Session 7). Generalized to match the any-wikilink-type design.
27. **AlignmentOutput.verdict uses Literal, not VaultVerdict enum** (Session 7, /simplify review). The LLM should only return 3 of VaultVerdict's 6 values; Literal constrains the structured output correctly.
28. **Full-vault fallback for cited-note lookup** (Session 7, user-reported bug). `evaluate_alignment()` accepts an optional `full_vault_by_name` (unfiltered vault) as fallback when a cited note isn't in the argument_pyramid-filtered vault. Eliminates false `note_not_in_vault` for notes that exist but aren't pyramid-tagged. Filtered vault is still used for TG 02.5 batch matching (appropriate — batch matching should scope to the paper).
29. **Phase 02 milestone accepted via spot-check** (Session 8, user decision). The 02.4.4/02.5.4 live run exercised all code paths; full-paper run judged unnecessary. Scale behavior (~450-claim batch matching in one context) remains untested — known, accepted risk.
30. **Corpus RAG split out to Phase 04** (Session 8, user decision). Phase 03 = triage + routing + web reuse + orchestration only. The router must be an extension point: routes declared by manifest, handlers share a common interface, policy consults capabilities — adding a route touches only the registry and policy table. Future routes beyond corpus: specialist DB searches via API.
31. **Web route is triage-gated** (Session 8, user decision). Web search runs only for triage-passed claims; trivial and novel-result/dataset-dependent claims never hit web.
32. **First-client principle for doc-rag-backend** (Session 8, user directive — recorded in Phase 04 roadmap entry). We own both repos, sole users. Phase 04 approaches api.ragtogo.com as its first genuine client, records client needs, and feeds improvements back via direct edit + redeploy (Hetzner) or a cross-repo communication note actioned by an agent in the doc-rag-backend repo. Improvements must not degrade other potential clients. Backend facts: live on Hetzner, likely test + prod DBs, some ukraine sources probably ingested (unconfirmed).
33. **Phase 03 milestone = standard test file** (Session 8, user decision). `ukraine-intro-test.txt` routed heavy run; full-paper runs post-phase optional.

### Test suite

245 tests total (242 pass with `-m "not slow"`, 3 slow tests deselected).

| File | Count | Covers |
|------|-------|--------|
| test_models.py | 24 | MODEL_REGISTRY, tier resolution, provider routing, reasoning effort |
| test_settings.py | 13 | Pydantic settings, env var validation |
| test_ingest.py | 31 | PDF extraction, chunking, text dispatch, report rendering |
| test_cost_tracking.py | 12 | Search cost counter, estimates, free-tier balance, print_summary |
| test_config.py | 7 | TOML loading, sections, fallbacks, real config.toml validation |
| test_claim_record.py | 23 | ClaimRecord, enums, DraftPosition, RouteVerdict, serialization |
| test_run_config.py | 20 | ResourceManifest, RunProfile, available_routes, vault-less degradation |
| test_draft_parser.py | 25 | Wikilink parsing, stripping, author-year detection, sentence splitting, ParsedDraft |
| test_citation_binder.py | 15 | Citation binding via original_index, union semantics, decomposition survival |
| test_vault_serializer.py | 24 | Vault note parsing, filtering, serialization, token counting (22 narrow + 2 slow live vault) |
| test_alignment.py | 22 | gather_evidence (8), evaluate_alignment (12 + 2 fallback, async with mocked LLM) |
| test_vault_match.py | 14 | batch_match_claims (5), verify_matches (9, async with mocked LLM) |
| test_gap_report.py | 14 | assign_suggested_actions (7), render_gap_report (5), serialize_results (2) |
| test_ingest.py (slow) | 1 | Docling PDF extraction (~16s) |

### Phase 02 new files (Sessions 6–7)

| File | Purpose |
|------|---------|
| `utils/claim_record.py` | ClaimRecord, CitationStatus, VaultVerdict, SuggestedAction, DraftPosition, RouteVerdict |
| `utils/run_config.py` | ResourceManifest, RunProfile |
| `docs/playbook/claim-record-design.md` | Attribute taxonomy — which phase populates each field |
| `ingest/draft_types.py` | Shared types: WikilinkCitation, ParsedSentence, ParsedDraft |
| `ingest/draft_parser.py` | Wikilink parsing, author-year detection, sentence splitting, parse_draft() |
| `ingest/citation_binder.py` | bind_citations(verdicts, parsed_draft) → List[ClaimRecord] |
| `ingest/vault_serializer.py` | VaultNote, SerializedVault, parse_vault_note(), load_vault(), serialize_vault() |
| `ingest/alignment.py` | gather_evidence() (one-hop vault traversal) + evaluate_alignment() (high-tier LLM) |
| `ingest/vault_match.py` | batch_match_claims() (mid-tier batch) + verify_matches() (high-tier adversarial) |
| `ingest/gap_report.py` | assign_suggested_actions(), render_gap_report(), serialize_results() |
| `scripts/spot_check_vault.py` | Live spot-check for alignment + vault matching against real vault |
| `workspace/inbox/ukraine-rich-wikilinks-test.md` | Test excerpt with 7 wikilinks across 4 note types |
| `tests/fixtures/vault/` | 6 fixture vault notes for offline testing |

---

## Recent Sessions

| Date | What was done |
|------|---------------|
| 2026-07-22 | Session 1: Fork, clone, PM setup, assessment artifact, websearch-and-costs doc |
| 2026-07-22 | Session 2: Flatten to agent-only, OpenRouter + tier-based registry, PDF ingest (Docling), /claimify skill, NLTK fix, OpenAI live test, tier rebalancing, model selection playbook, Sonnet 5 hybrid-reasoning correction. 63 tests. 13 commits. |
| 2026-07-23 | Session 3: Reasoning effort fix, search cost tracking, dead export cleanup, config.toml extraction, OpenRouter live test, Exa vs Tavily comparison, architecture audit. 87 tests. 7 commits. |
| 2026-07-23 | Session 4: Emoji fix in dev.py, design discussion on academic verification scope, Phase 02 plan written, first full academic paper PDF test (448 claims, $10 cost with analysis). |
| 2026-07-23 | Session 5: Phase 01 closed (01.5.3 /claimify skill e2e test passed via OpenRouter after OpenAI 429). Phase 02 approved. Standard dev test file established. Vault corrections: 98->93 across 9 notes with [sic] on de Carvalho source notes; 12th->11th ESS in commission brief with rerun warning. 4 commits. |
| 2026-07-23 | Session 6: Phase 02 TGs 02.1–02.3 implemented. Data models (ClaimRecord, ResourceManifest, RunProfile), draft parsing + citation binding, vault serializer with live vault validation. 107 new tests (195 total). CLAUDE.md key files updated. |
| 2026-07-23 | Session 7: Phase 02 TGs 02.4–02.6 implemented. Cited-claim alignment (any wikilink type + one-hop traversal + full-vault fallback), citation-free vault matching (mid-tier batch + high-tier verify), gap report with suggested actions. Live spot-check passed (OpenRouter): all 7 cited notes vault_supported, 9/15 citation-free matched, gap report rendered. Design corrections: any-wikilink-type, one-hop traversal, NOTE_NOT_IN_VAULT rename, full-vault fallback. 50 new tests (245 total). 3 commits. |
| 2026-07-24 | Session 8: Phase 02 CLOSED (milestone accepted via spot-check, docs-align-check clean — zero drift). Phase 03 planned via Fable orchestration (3 Haiku explore agents: data contract, doc-rag-backend knowledge, web-route reuse surface), restructured after user design review (corpus RAG → Phase 04; router extensibility requirement added), approved. Roadmap renumbered: 04 corpus RAG (with first-client directive), 05 deep research, 06 draft update loop. No code changes. |
