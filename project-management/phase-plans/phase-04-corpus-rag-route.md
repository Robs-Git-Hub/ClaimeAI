# Phase 04: Corpus RAG Route

**Status:** APPROVED (user sign-off, Session 9). Environment: prod-first with devtest fallback approved; cross-repo commits to doc-rag-backend approved; API key to be retrieved from backend deploy env or freshly generated (user holds no copy).
**Goal:** Register a `"corpus"` verification route backed by doc-rag-backend (`api.ragtogo.com`) so claims whose evidence lives in the paper's source documents — the novel-result and dataset-dependent claims that never route to web — can be verified against full-text sources. ClaimeAI acts as the backend's **first genuine client**: client needs are recorded and fed back without degrading the backend for other potential clients.

---

## Context

### The problem this phase solves

Phase 03 ends with never-web claims (novel-result, dataset-dependent) marked `unverifiable-by-available-routes` when the vault misses them — honest, but a dead end. Their evidence lives in the full text of the paper's cited sources. doc-rag-backend already ingests, chunks, enriches, and embeds academic PDFs and serves hybrid (dense + FTS + RRF) search over them. Phase 04 connects the two.

### What already exists (verified Session 9 prep)

- **Router extension point is real and proven.** Adding a route = handler function + `ROUTE_HANDLERS["corpus"]` registration + `"corpus"` in the never-web policy row's `candidate_routes` + one `available_routes` check on `manifest.corpus_ids`. The never-web row's code comment already anticipates this. Orchestrator, gap report, and `ClaimRecord` are route-agnostic — no changes. (`tests/test_routing.py` extensibility test is the template.)
- **`ResourceManifest.corpus_ids` is reserved** (Phase 02 contract) but `available_routes` does not yet consult it.
- **Evidence summarization is reusable by design.** `summarize_evidence_for_claim(claim_text, evidence_items)` is route-agnostic; corpus passages wrap as `Evidence(url, text, title)` items and flow through the existing mid-tier summarize → high-tier evaluate chain.
- **Backend API contract (read from repo `main`, must be live-verified — see Risk 2):** `GET /search?q=&mode=hybrid&top_k=&document_ids=<comma-sep>` with `X-API-Key` header returns document-grouped chunks with text, section, enrichment context, scores, paper summary, section outline. `GET /documents` (paginated) returns full metadata (title, authors, DOI, OpenAlex ID, Zotero key). `GET /health` is unauthenticated.
- **Confirmed client-need gap (first first-client finding):** no server-side search by author/title/DOI/Zotero — the client must fetch `/documents` and map metadata → `document_ids` itself.
- **Ingested content:** 5 eval documents including three ukraine-paper sources (Kim 2023, Nurullayev & Papa 2023, Zeng 2026). Whether these are in the **prod** DB (Supabase `prod-ragtogo` + Pinecone `doc-rag-prod`) or only **devtest** is unconfirmed — discovery task.
- **Backend repo state:** cloned at `../doc-rag-backend` on `main`; `origin/dev` was 6 commits ahead at clone time (migration 008, Zotero corpus discovery, env refactor). The dev-branch HANDOVER is the freshest statement of deployed state.

### Design pillars

1. **First-client discipline** (user directive, Session 8). Record client needs (DB content visibility, metadata search, API help/docs) as they are encountered. Improvements flow back via direct edit + redeploy to Hetzner, or a cross-repo communication note actioned by an agent in the doc-rag-backend repo. Improvements must not degrade other potential clients.
2. **Manifest stays the authority.** The corpus route exists only when `manifest.corpus_ids` is declared; absence is a no-op, not an error.
3. **Extensibility validated with a second real route.** Adding corpus must touch only the route registry, the policy table, `available_routes`, and new client code — not the orchestrator, report, or data model. If it needs more, that is a design finding to surface, not silently absorb.
4. **Reuse, don't rebuild.** Corpus passages become `Evidence` items; summarization and high-tier evaluation are the existing components.
5. **Quality gate carried forward.** Corpus evidence is evaluated at the `high` tier — same gate as web and vault. Never downgrade.
6. **Two-stage cost shape.** Scoped hybrid search (cheap, self-hosted) → mid-tier summarization → high-tier evaluation. Marginal search cost is near zero vs Exa; LLM spend follows the Phase 03 pattern.

### Test corpus and milestone

**Standard dev test file:** `workspace/inbox/ukraine-intro-test.txt` (15 claims). The three dataset-dependent claims that Phase 03 correctly routes away from web are the motivating cases: success looks like those claims receiving corpus verdicts (supported, contradicted, or honestly insufficient with provenance) instead of `unverifiable-by-available-routes`. Full-paper runs remain optional post-phase validation.

## Dependencies

- Phase 03 complete (router, triage, evidence summarization, `run_heavy.py`).
- doc-rag-backend live at `api.ragtogo.com`; sibling clone at `../doc-rag-backend`.
- Backend API key (from the backend's production env — obtain from user or backend deploy conventions; never committed).
- OpenRouter credit for the milestone run (OpenAI still out of credit).

## Task Groups

### TG 04.1: First-Client Discovery (live)

**Goal:** Ground-truth the deployed API and its content; decide the target environment; make the first client-needs record in the backend repo.

**Success criteria:**
- Freshest backend state read from the dev-branch HANDOVER (no local checkout of dev needed).
- Live `GET /health` and `GET /documents` against prod verified; actual response shapes compared against the repo-read contract; which ukraine sources are present, and their `document_ids`, recorded.
- Environment decision recorded in this plan (default: **prod** — the genuine-client experience; devtest fallback only if prod lacks the documents).
- First client-needs communication note committed in the doc-rag-backend repo (metadata-search gap + anything discovery surfaces), per the cross-repo convention.

**Constraints:**
- Read-only against the API. No ingestion, no mutation, no backend deploys or dev→main merges without explicit user approval.
- The API key is a secret: goes in ClaimeAI `.env`, referenced in `.env.example` by name only.

### TG 04.2: Corpus Client

**Goal:** An HTTP client module (`ingest/corpus_client.py`) for scoped search and document listing, with metadata mapping (DOI / author / title / Zotero ref → `document_ids`), plus config and settings plumbing.

**Success criteria:**
- TDD: `tests/test_corpus_client.py` written first, green with mocked HTTP (NARROW). Covers: search request shape (query, `document_ids` scoping, `top_k`, auth header), response parsing into typed models, document-list pagination, metadata mapping, API-unreachable degradation.
- `[corpus_api]` section in `config.toml` (base URL, search defaults); `RAG_API_KEY` in `utils/settings.py` with the established validator pattern; `.env.example` updated. Settings/config additions covered in `test_settings.py` / `test_config.py` (NARROW).
- API failure degrades gracefully (stage error / handler-failure path), never aborts a run.

**Constraints:**
- Do not enable Cohere reranking (backend lesson L018: free tier rate-limits silently — all calls can fail with no error). `mode=hybrid` default.
- Client-side metadata mapping is the accepted pattern for now (the server-side gap is a recorded client need, not something to hack around).

### TG 04.3: Corpus Route Handler and Policy

**Goal:** `corpus_route_handler` registered as a real route: search → wrap chunks as `Evidence` → `summarize_evidence_for_claim` (mid tier) → high-tier evaluation → `RouteVerdict(route="corpus")` with document-id + section/chunk provenance.

**Success criteria:**
- Corpus verdict vocabulary defined and recorded in `docs/playbook/claim-record-design.md` (expected shape: supported / contradicted / insufficient / no-hit — implementing session finalizes names).
- TDD (NARROW): handler verdict shape and provenance, registration, never-web claims route to corpus when the manifest declares `corpus_ids`, manifest gating (no `corpus_ids` → no corpus route), handler failure recorded in `routing_reason`.
- `available_routes` consults `corpus_ids`; the never-web policy row's `candidate_routes` includes `"corpus"`.
- MID regression: full non-slow suite green; gap report shows corpus verdicts **without any report-code changes** (pillar 3 check).

**Constraints:**
- Evaluation tier is `high` — never downgrade (house quality gate).
- Summarization must preserve refuting content — reuse the existing component and its safeguards; do not fork a corpus-specific summarizer.
- If the route cannot be added within the registry + policy + `available_routes` surface, stop and surface the design finding.

### TG 04.4: Orchestration and Milestone

**Goal:** `run_heavy.py` accepts corpus scoping; milestone run proves the route end-to-end.

**Success criteria:**
- CLI accepts corpus scoping (e.g. `--corpus-ids` and/or a mapping produced by the client module from TG 04.1 discovery); manifest wired through; covered by orchestration tests (NARROW → MID).
- **MILESTONE (FULL, live):** heavy run on `ukraine-intro-test.txt` with vault + corpus declared. The three dataset-dependent claims receive corpus verdicts with document-id provenance (or an honest insufficient — never fabricated support). Routing decisions visible in the report. User judges the report useful — user judgment is the gate. Wall-clock and cost recorded.

**Constraints:**
- Live spend at the milestone only; standard test file is the gate; full-paper run is post-phase and user-triggered.

### TG 04.5: Quality & Wrap

**Goal:** Docs aligned; client-needs improvements fed back; session wrapped.

**Success criteria:**
- `docs-align-check` clean. CLAUDE.md (key files, pipeline diagram, env vars), `claim-record-design.md`, `docs/websearch-and-costs.md` (corpus cost profile), TASKS.md, HANDOVER.md all current.
- Cross-repo note(s) in doc-rag-backend for every client-need gap confirmed this phase.
- Pushed to origin.

## Phase Success Criteria

- Corpus route registered and exercised end-to-end on the milestone file; the three dataset-dependent claims resolved via corpus (or honestly insufficient with provenance).
- No changes were needed to `execute_routing`, the gap report, or `ClaimRecord` — extensibility pillar validated by a second real route.
- A client-needs record exists in the doc-rag-backend repo.
- Offline suite green (340+ tests); light-profile behavior unchanged.

## Risks and known failure modes

1. **Prod DB may not contain the ukraine sources** (eval seed may be devtest-only). Mitigation: discovery TG runs first; devtest fallback; ingestion into prod only with user approval.
2. **Repo `main` lags `dev`** — the API contract read from `main` may be stale vs the deployed service. Mitigation: live-verify response shapes in TG 04.1 before writing client models.
3. **Retrieval misses at chunk granularity** — a claim's evidence may span chunks or be absent. Mitigation: `top_k` tuning within reason; report insufficient honestly; never fabricate support (Phase 02 lesson: plausible-but-wrong is worse than no match).
4. **Summarization bias** dropping refuting passages (Phase 03 Risk 4 carried forward). Mitigation: reuse the existing summarizer with its keep-contradicting-content instruction and config switch.
5. **Scope creep into the backend.** This phase records client needs; it does not implement backend features unless trivial and user-approved. Deploys and merges in doc-rag-backend are user-gated.
6. **Backend load under parallel search** — self-hosted app with a 3GB memory limit. Mitigation: routing already bounds concurrency (`Semaphore(5)`); watch latency during the milestone run.

Advisory (backend lessons manifest, matched during prep): L013/L014 (LLM-as-judge needs structured output and low temperature) are already satisfied by reusing the existing structured-output high-tier evaluation path — do not build a new judge. L018 is a hard constraint in TG 04.2.

## Roadmap after this phase

| Phase | Contents |
| ----- | -------- |
| 05 — Deep Research Commissions | Human-approved escalation, commission writer, response-paper ingestion + re-evaluation |
| 06 — Draft Update Loop | Propose citation-inserting draft edits after vault improvement |

**Edge-case backlog** (unchanged from Phase 03): PDF-only drafts; source fetching for absent papers; vault-less heavy runs; vault QA / chain completeness; semi-automated vault enrichment; triage-aware `suggested_action` pass (Session 8 handover flag).
