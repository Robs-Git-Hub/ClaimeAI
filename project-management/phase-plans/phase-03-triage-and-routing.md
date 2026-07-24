# Phase 03: Triage & Routing

**Status:** COMPLETE (Session 8, 2026-07-24). Planned, amended twice, implemented, and milestone-accepted in a single session. TGs 03.1–03.5 fully implemented; TG 03.6 wrap complete. Amendments: TG 03.4 Evidence Summarization added mid-session (user cost principle #1); TG 03.5 Pipeline Parallelization added after milestone review (wall-clock reduction); full-vault fallback promoted to high tier + contradiction-seeking prompt added after the "98 votes" vault recall failure.
**Goal:** Route every claim to the cheapest verification method that can actually verify it. Triage first, then route: vault (Phase 02) or web (Phase 01), with web spend gated by triage. The router is built to be extended — corpus RAG (Phase 04) and future routes (e.g. specialist DB searches via API) plug in without rework.

> **Scope decision (user, Session 8):** corpus RAG via doc-rag-backend is split out to **Phase 04** — planning and implementation, including the first-client discovery of api.ragtogo.com. Phase 03's job is the self-contained cost win (triage + routing + web reuse + production orchestration) and a router designed for additional routes. Vault QA (verifying vault notes against original sources) remains a separate backlog capability — a different domain of work from draft-claim verification.

---

## Context

### The problem this phase solves

Phase 02 leaves `no_vault_match` claims unresolved — they appear in the gap report as dead ends. Phase 01's web route exists but treats all claims uniformly: the Session 4 full-paper run cost ~$10 and produced misleading "Refuted" verdicts on novel-result claims that no web source could ever contain. The user's three cost principles (Session 4) diagnose the root cause as uniform treatment and prescribe the fix this phase implements:

1. Triage is the primary cost lever — trivial claims get cheap-and-fast, load-bearing claims get thorough verification.
2. Claims route to the method that can actually verify them — novel results go to vault (or, in Phase 04, corpus), never web.
3. The expensive evaluator judges summarized evidence, not raw dumps.

### What already exists (verified Session 8 exploration)

- **Data contract is ready.** `ClaimRecord` carries Phase 03 placeholder fields (`triage_class`, `citation_expectation`, `importance`), `RouteVerdict` is route-generic (`route: str`), and `ResourceManifest` has `corpus_ids` reserved for Phase 04. Phase 03 populates fields; no schema rework.
- **Web route is reusable per-claim.** `claim_verifier` accepts `{"claim": ValidatedClaim}` via `ainvoke()` and returns a `Verdict` — no re-extraction needed (this is how `fact_checker/nodes/claim_verifier.py` already calls it).
- **Integration debt.** Phase 02 functions (alignment, vault matching, gap report) are only wired together in `scripts/spot_check_vault.py` — demo wiring, not a production entry point (Session 7 handover flag). This phase pays that down.

### Design pillars

1. **Triage before spend.** Web search runs only for claims triage marks as important enough and of a type web can verify (user decision, Session 8). Trivial claims and novel-result claims never hit the web.
2. **Conservative triage.** A misclassified load-bearing claim is a silent verification miss. When the classifier is uncertain, classify *up* (more verification), not down. Cheap-broad-then-careful-verify remains the house pattern.
3. **The router is an extension point** (user directive, Session 8). Adding a route must be straightforward: Phase 04 adds corpus RAG; future routes may include specialist database searches via API. Concretely: routes are declared by the manifest (`available_routes`), route handlers share a common interface (claim in → RouteVerdict out), and the routing policy consults capabilities rather than hardcoding route names into its logic. Adding a route should touch the route registry and the policy table — not the orchestrator, the report, or the data model.
4. **Reuse, don't rebuild.** The web route is the existing `claim_verifier` graph invoked per-claim.
5. **The manifest stays the authority.** A route exists only when the manifest declares its resources; absence is a no-op, not an error (Phase 02 pillar 3 carried forward).
6. **Populate, don't redesign.** Phase 03 fills the placeholder fields the Phase 02 contract reserved. Any vocabulary chosen (triage classes, citation-expectation values) is recorded in `docs/playbook/claim-record-design.md`.

### Test corpus and milestone

**Standard dev test file:** `workspace/inbox/ukraine-intro-test.txt` (user decision, Session 8 — milestone gate). Characterized behavior: 15 claims, including **three dataset-dependent claims web search can't verify** — the motivating cases. Their evidence lives in the vault (author's own RESULT notes), so success looks like: those three route away from web, trivial claims are marked trivial, and web spend drops relative to the Phase 01 baseline on the same file.

Full-paper routed runs are NOT part of the Phase 03 gate; they remain available as optional post-phase validation when the user chooses to spend the credit.

## Dependencies

- Phase 02 complete (TGs 02.1–02.6 done; 02.7 spot-check accepted).
- OpenRouter credit for live spot-checks (OpenAI still out of credit as of Session 5).
- No doc-rag-backend dependency — deliberately excluded from this phase.

## Task Groups

### TG 03.1: Triage Classifier

**Goal:** Populate `triage_class`, `citation_expectation`, and `importance` on every ClaimRecord, cheaply, in batch.

**Success criteria:**
- A documented vocabulary for `triage_class` (covering at minimum: trivial/common-knowledge, novel-result/own-work, dataset-dependent, general-factual, academic-citable) and `citation_expectation`, recorded in `claim-record-design.md`.
- Batch classification: one LLM call over all claims of a draft (mid tier or below), not per-claim calls. Cost scales sub-linearly with claim count.
- Offline tests with mocked LLM; classification of the standard test file's 15 characterized claims matches expectations (the 3 dataset-dependent claims classified as such; spot-checkable live for cents).
- Uncertain classifications degrade conservatively (toward more verification, never toward "trivial").

**Constraints:**
- Triage must never be a hard gate on vault verification — vault routes are nearly free and always run (Phase 02 behavior unchanged).
- `importance` is 1–5 per the existing contract; where a claim matched a vault CLAIM note in Phase 02, do not overwrite `claim_strength`/`evidence_quality` — triage importance is a separate field.

**Context:** Triage is the primary cost lever (Session 4 principles). The classifier's output drives TG 03.2 routing. Expect prompt iteration against the characterized test file.

### TG 03.2: Routing Policy and Route Registry

**Goal:** A deterministic routing function plus the route-handler abstraction that makes future routes (corpus RAG in Phase 04, specialist DBs later) additive.

**Success criteria:**
- Pure routing function over (ClaimRecord attributes × manifest.available_routes) → route decision; fully offline-testable, no LLM call.
- Encodes the agreed policy: vault-supported/contradicted claims stop (verdict exists); trivial claims stop (verification unnecessary); novel-result and dataset-dependent claims never route to web; web runs only for triage-passed claims when the manifest enables it; claims no available route can verify are marked explicitly (e.g. `unverifiable-by-available-routes`), not silently dropped.
- A route-handler interface (claim record in → RouteVerdict out) with the web route as its first implementation, invoking the existing `claim_verifier` graph per-claim (`{"claim": ValidatedClaim}` → `Verdict`), recorded as a `route="web"` RouteVerdict.
- **Extensibility proof:** a test registers a fake route (stub handler + manifest declaration + one policy-table row) and the pipeline routes to it — demonstrating that a new route touches only the registry and the policy table.
- Routing decisions and their reasons appear on the claim record (auditable in the report).

**Constraints:**
- The policy is code, not prompt — routing must be reproducible and unit-tested. LLM judgment enters only via the triage fields it consumes.
- A wrong "don't verify" is worse than a wasted verification; ties break toward verifying (mirrors TG 03.1's conservative constraint).
- Don't over-abstract: the interface exists to make Phase 04 additive, not to speculate about every future route's needs. Two real implementations (web now, corpus in Phase 04) are the design's validation.

**Context:** This is where the Session 4 principles become behavior. The routing table itself (which triage class × citation status → which route) is drafted by the implementer and reviewed with the user before the milestone run.

### TG 03.3: Orchestration and Report Extension

**Goal:** One production entry point that runs the full heavy pipeline end-to-end — parse → extract → bind → vault verify → triage → route → web — and a gap report that shows the routing story.

**Success criteria:**
- A runnable script or graph (extending `scripts/run_from_pdf.py` or a new `scripts/run_heavy.py` — implementer's call) that takes a draft + manifest and produces `results.json` + `report.md` in `workspace/output/<stem>/`, replacing the standalone spot-check-script wiring left after Phase 02.
- Gap report extended: per-claim triage class, route taken, route verdicts with provenance; a cost/route summary section (how many claims took each route, web calls avoided vs. Phase 01 baseline).
- Report sections stay manifest-adaptive: routes not declared don't appear; light profile output remains Phase 01-compatible (regression-tested).

**Constraints:**
- Positions and provenance survive end-to-end (Phase 02 pillars carried forward).
- Offline test suite covers the orchestration path with mocked LLM; live runs reserved for the milestone.

**Context:** HANDOVER (Session 7) flagged that Phase 02 functions were never wired into production entry points — `spot_check_vault.py` is demo wiring. This TG pays down that integration debt as part of delivering the routed pipeline.

### TG 03.4: Evidence Summarization (added by amendment, Session 8)

**Goal:** Cut the web route's high-tier input cost: a cheap model extracts claim-relevant evidence from raw search results before the high-tier evaluation judges it.

**Success criteria:**
- A summarization step in `claim_verifier`'s evidence path: low or mid tier condenses raw search results into claim-relevant extracts; `evaluate_evidence` (high tier, unchanged) judges the extracts, not raw dumps.
- Summaries preserve refuting as well as supporting content, and retain source attribution (URL) so provenance survives to the verdict.
- Config-switchable in `config.toml` (on by default; off restores current behavior) — enables A/B comparison and a safe rollback.
- Token accounting: raw vs. summarized evidence sizes logged (extend the existing cost-tracking logging pattern) so the saving is measurable, not assumed.
- Offline tests with mocked LLM; a live cost-delta measurement on the milestone file's web-routed claims is recorded at wrap.

**Constraints:**
- Evaluation itself never drops below `high` tier (standing rule) — this TG changes what the evaluator reads, not who evaluates.
- The summarizer must be instructed against support-bias: contradicting/exculpatory evidence must survive summarization. A spot-check comparing verdicts with summarization on vs. off on the same claims is part of acceptance.
- Changes confined to the `claim_verifier` evidence path; light-profile behavior with the switch off must be byte-compatible.

**Context:** Session 4 cost analysis: 76% of the $10/paper cost sat in the high tier, much of it input tokens — Exa returns ~30KB, Tavily up to ~1.1MB of raw content per run (Session 3 comparison). This is user cost principle #1 ("intelligence is for judgment, not for reading"). The Phase 04 corpus route reuses this component for retrieved passages — build it as a reusable summarize-before-judge step, not a web-only special case.

### TG 03.5: Pipeline Parallelization (added by amendment, Session 8)

**Goal:** Cut wall-clock time by parallelizing independent LLM calls that are currently sequential, with no changes to prompts, models, or verdict logic.

**Success criteria:**
- Voting loops (selection + disambiguation): all sentences vote concurrently instead of sequentially. For N sentences × 3 votes, wall-clock drops from N sequential rounds to ~1 round (the 3 votes per sentence are already parallel; this parallelizes across sentences).
- Web verification: claims routed to web are verified concurrently (bounded by a semaphore to avoid rate limits) instead of one at a time through the claim_verifier graph.
- Vault verify: per-proposal verification calls run concurrently instead of sequentially.
- Offline test suite stays green (correctness unchanged — these are pure concurrency changes to independent work items).
- Measurable wall-clock improvement on the standard test file vs. the pre-parallelization baseline.

**Constraints:**
- Concurrency must be bounded (semaphore) — OpenRouter and Exa both have rate limits. A reasonable default (e.g. 5–10 concurrent) should be config-settable or at least a module constant.
- Do not change any prompts, model tiers, or verdict semantics — this is purely a latency optimization.
- The voting quality gate (2/3 majority) must be preserved exactly — parallelizing across sentences doesn't change the per-sentence voting logic.

**Context:** The Session 8 milestone re-run on the 250-word test file took ~13 minutes. Bottleneck analysis showed ~60+ sequential API rounds where ~15–20 would suffice. The three parallelization targets (voting loops, web verification, vault verify) are all independent-item loops with no cross-item dependencies. Extraction caching (content-hash → skip re-extraction on re-runs) is a nice-to-have but not required for this TG.

### TG 03.6: Quality & Wrap

**Goal:** Prove the phase milestone and leave the project handover-clean.

**Success criteria:**
- **Milestone:** a routed heavy run on `workspace/inbox/ukraine-intro-test.txt` completes; the 3 dataset-dependent claims route away from web; triage and route decisions are visible in the report; the user judges the report useful (acceptance gate).
- Light-profile regression: non-vault run still behaves like Phase 01.
- Offline suite green; `docs-align-check` run; CLAUDE.md, claim-record-design.md, TASKS.md, HANDOVER.md current; pushed to origin.

**Constraints:**
- Live runs spend credit — milestone-only, standard test file only (full-paper run is post-phase optional, user-triggered).
- Run `docs-align-check` before wrap (Phase 02 lesson: don't defer it).

## Success Criteria (phase)

- The standard test file, run heavy with vault + web declared, produces a report where every claim shows: triage class, route(s) taken, verdict(s) with provenance, suggested action — and the three dataset-dependent claims demonstrably avoid the web route.
- Web spend on the test file is measurably below the ungated Phase 01 baseline for the same file — via both levers: fewer web calls (triage gating) and cheaper web calls (evidence summarization, with the raw-vs-summarized token delta recorded).
- Adding a route is demonstrably additive (the fake-route extensibility test passes; Phase 04's corpus route is the real-world validation).
- A manifest without web (or without vault) degrades cleanly — routes absent, run intact.

## Risks and known failure modes

- **Triage misclassification.** A load-bearing claim marked trivial is silently unverified. Mitigation: conservative-up classification, characterized-file spot-checks, routing table reviewed by user before milestone.
- **Premature abstraction in the route interface.** Designing for imagined future routes bloats Phase 03. Mitigation: the interface is validated by exactly two real routes (web now, corpus in Phase 04); anything more speculative is out of scope.
- **Orchestration scope creep.** Wiring the full pipeline could balloon into refactoring Phase 01/02 internals. Mitigation: orchestration composes existing functions; internal changes to extraction/vault modules are out of scope unless a bug blocks the milestone.
- **Summarization bias.** A summarizer that quietly drops refuting evidence turns "Refuted" claims into "Supported" ones — worse than the cost it saves. Mitigation: explicit keep-contradicting-content instruction, verdict A/B spot-check (summarization on vs. off) as part of TG 03.4 acceptance, config switch for rollback.

## Roadmap (after Phase 03)

| Phase | Contents |
|---|---|
| **04 — Corpus RAG route** | doc-rag-backend as an evidence route. Includes the **first-client discovery** of api.ragtogo.com (user directive, Session 8: we own both repos and are sole users — approach the API as its first genuine client; record client needs — DB content visibility, search by author+title/DOI/Zotero ref, API help/docs; improvements flow back via direct edit + redeploy to Hetzner, or a cross-repo communication note actioned by an agent in the doc-rag-backend repo; improvements must not degrade other potential clients). Then the client: `GET /search` scoped by `manifest.corpus_ids`, `"corpus"` route registered, evidence judged at `high` tier with document-id provenance. Backend facts known now: live on Hetzner; likely test + prod DBs; some ukraine sources probably ingested (unconfirmed). |
| **05 — Deep research commissions** | Escalation candidate selection (human-approved), commission document writer, response-paper ingestion and re-evaluation |
| **06 — Draft update loop** | Propose draft edits (insert citations) after vault improvement; "would a peer reviewer ask for evidence?" trigger |

**Edge-case backlog** (unchanged): PDF-only drafts / plain-text citation binding; source fetching for absent papers; vault-less heavy runs; **vault QA / chain completeness** (verify vault notes against original source docs — a separate domain from draft-claim verification; will likely reuse doc-rag-backend for source text retrieval); semi-automated vault enrichment.
