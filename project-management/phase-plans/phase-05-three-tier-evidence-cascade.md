# Phase 05: Three-Tier Evidence Cascade

**Status:** COMPLETE (Session 12). TGs 05.1–05.5 all done. 488 tests (488 non-slow). Cascade + source-conflict both demonstrated live. Session 12 added D10 amendment (support confirmation), alias-based note resolution, and the conflict-demo fixture that satisfied the source-conflict milestone.
**Goal:** Rework routing so the three evidence sources — vault, corpus, web — form a domain-general verification cascade that any claim can traverse, replacing the Phase 04 scope line that reserved the corpus route for never-web claims only. Add independent-lineage double-checks for high-importance findings and pure-code conflict detection between tiers.

---

## Why this amendment exists

The Phase 04 milestone run (Session 10, standard test file) exercised the full pipeline with vault + corpus + web all declared — and **zero claims reached the corpus route**. Triage correctly classified every claim as trivial / general-factual / academic-citable (UN vote tallies are public records, per the Session 8 triage fix), so no claim hit the `never-web` policy row, which is the only row whose `candidate_routes` includes `"corpus"`. The corpus infrastructure worked (hybrid search live-verified, 3 papers ingested); the *policy* never sent anyone there.

The user's review identified this as a design error, not a test-file gap: the scope line "corpus only for never-web claims this phase" (Decision 44, Session 9) hard-wires an impoverished view of what a corpus is for.

### The live demonstration case ("98 votes")

The draft claims support for a European-backed Ukraine resolution fell to **98 votes** by February 2025.

- **Web verdict (Session 10 run):** Refuted — BBC, Al Jazeera, UN sources say **93**.
- **Corpus content (de Carvalho 2025, ingested):** states the European-backed resolution (L10) "registered **98** votes in favour".
- **Vault history:** Session 5 corrected 98→93 across 9 notes — the error entered the vault *from the corpus source*.

A cited source and the web consensus genuinely disagree. Under the current policy the corpus is never consulted, so the report can only say "web refutes" — it cannot say the far more useful thing: *"your cited source says 98, but independent sources say 93 — the source itself may be wrong."* Under a naive next-tier-up double-check, corpus would "confirm" the vault and the error would survive. Both failure modes are fixed by the design below.

## The evidence model

Three sources, distinguished by **what they are authoritative for** and by **provenance lineage**:

| Tier | Contains | Authoritative for | Lineage | Marginal cost/claim | Latency |
|------|----------|-------------------|---------|--------------------:|---------|
| Vault | Key information extracted from sources, plus our own observations and experiments | "What have we already established?" | Derived from corpus + own work | ~$0.001 (batched) | One batch |
| Corpus (RAG) | Full text of source documents — specialist content beyond the vault summary, often not on the web | "What does the cited source actually say?" | The sources themselves | ~$0.01–0.02 (self-hosted search ≈ free; mid summarize + high evaluate) | Fast, no iteration loop |
| Web | General information | "What is the world's independent consensus?" | Independent of vault and corpus | ~$0.05–0.10 (search fees + iterative loop) | Slowest |

Two structural facts drive the whole design:

1. **Cost, speed, and specificity all order the same way** (vault < corpus < web), so a cheapest-first cascade is also the fastest and most-specific-first design.
2. **Vault and corpus share one lineage** (the vault is largely extracted *from* the corpus). Web is the only independent source. Checking vault against corpus can confirm a shared error — the 98-votes case illustrates this risk. Session 12's D10 amendment (support confirmation) closes the gap: supported claims now get web confirmation when important.

## Design decisions (user-approved, Session 10)

**D1 — Cascade, cheapest first.** Vault batch runs first for all non-trivial claims (unchanged). Claims the vault leaves silent go to corpus (when declared in the manifest); claims the corpus leaves silent go to web (when eligible). Escalation triggers on *silent* verdicts only (see D6's normalization). Trivial claims search nothing at any tier (unchanged).

**D2 — Corpus is a general route.** All triage classes may use the corpus tier. Supersedes Decision 44 ("corpus only for never-web"). Never-web classes (novel-result, dataset-dependent) still never reach web — their cascade honestly ends at corpus, because the web cannot verify an author's own results.

**D3 — Citation-aware corpus scoping.** When a claim's citations (wikilinks or author-year strings) map to documents in the corpus, the corpus search is scoped to those `document_ids` (the client's `map_citations_to_document_ids()` exists for exactly this). Cheaper (smaller retrieval + summarize input) and more precise (it answers the attribution question directly). Unmapped/citation-free claims search the whole declared corpus scope.

**D4 — Attribution check for cited high-importance claims.** A claim with importance ≥ 4 whose citations map into the corpus gets a scoped corpus check **even if the vault already resolved it** — the vault cannot answer "does the source actually say this." This is the only path that produces vault-and-corpus verdicts on the same claim, and therefore the only source of D7's vault–corpus flag.

**D5 — Refutation confirmation via independent lineage.** A refutation from a single tier creates author work (revise the draft), so a false refutation is expensive. For claims with importance ≥ 4, a refutation recorded by only one tier gets one confirming check from a tier with **independent provenance — in practice, web** (not "the next tier up": vault↔corpus confirmation is circular per the lineage fact above). Exception: never-web classes have no independent tier; their single-lineage refutations (and supports) are reported as single-lineage rather than escalated (see D8). Supports do **not** trigger routine cross-checks — a vault-supported, citation-free claim stops at vault regardless of importance; cost stays sane.

**D6 — Conflict detection is pure code; no LLM referee.** Every route verdict normalizes to one of three values:

| Normalized | Route verdicts |
|------------|----------------|
| support | `vault_supported`, `corpus_supported`, web `Supported` |
| refute | `vault_contradicted`, `corpus_contradicted`, web `Refuted` |
| silent | `no_vault_match`, `note_not_in_vault`, `corpus_insufficient`, `no_corpus_hits`, web `Insufficient`, web `Conflicting` |

A conflict flag fires **only** on a clear support-vs-refute disagreement between tiers on the same claim. Silent or ambiguous verdicts never trigger it (web-internal `Conflicting` is that route's own ambiguity — it counts as silent here). The function is deterministic, LLM-free, and lives in report-assembly territory, in the same house style as `decide_route`. The referee is the author reading the gap report with both provenances in front of them.

**D7 — Two distinct flags from the same function.**
- Vault vs corpus disagree → **`vault-corpus-check-needed`**, listed under Vault Improvement Signals. It is a "re-read the source against your note" prompt, subject to human confirmation — not an automatic correction, because either side could be the stale one.
- Web vs (vault or corpus) disagree → **`source-conflict`** on the claim itself: "your source says X, independent sources say Y." This is the highest-value output the system produces. Originally illustrated by the 98-votes case; demonstrated live in Session 12 via the conflict-demo fixture (planted "140 votes" error caught by D10 web confirmation).

**D8 — Single-lineage honesty.** When a claim's only verdicts come from one lineage (vault/corpus) and no independent check is possible (never-web classes) or was warranted (importance < 4), the report annotates the resolution as single-lineage rather than presenting it with the same confidence as an independently confirmed one.

**D9 — Triage's role shifts; its prompt does not change.** Triage classes stop selecting *the* route (the cascade handles that) and instead determine (a) trivial skip, (b) web eligibility (never-web classes), (c) via importance, whether D4/D5 cross-checks apply. No re-prompting of the triage classifier is in scope.

## Amendment (Session 12)

**D10 — Support confirmation for important claims.** A claim whose vault or corpus verdict is a SUPPORT (per `normalize_verdict()` == support), with importance ≥ 4, web-eligible (triage class not in `NEVER_WEB_CLASSES`), and not already routed to web, gets **one** web confirmation check. Mixed support+refute still fires — no "no refute present" condition is added; web arbitrates. Implemented as `_needs_support_confirm()` in `ingest/routing.py`, dispatched alongside D4/D5 inside `apply_cross_checks()`. Config-switchable via `pipeline.support_confirmation` in `config.toml` (default on), following the exact pattern of `vault_match_fallback`.

This **supersedes D5's sentence "Supports do not trigger routine cross-checks"** for importance ≥ 4 claims. Rationale: a false fact shared by the author's vault and draft (the planted 140-vs-141 vote tally in `tests/fixtures/conflict-demo/`) previously sailed through with no independent check — vault-resolved claims stop routing entirely (D1's `vault-resolved` policy row), and D5's original guardrail meant a pure support verdict never triggered a cross-check either. Per the user's verification-conservatism principle ("better to send too much to web than too little; missed errors are the worst case"), the threshold used for D4/D5 (`CROSS_CHECK_IMPORTANCE_THRESHOLD = 4`) also gates D10 — user-approved this session at that same threshold rather than a separate, stricter one.

User-approved this session. Test coverage: `TestD10SupportConfirmation` in `tests/test_routing.py` (8 tests), plus two pre-existing D4/D5 tests (`test_d4_vault_resolved_cited_important_gets_corpus`, `test_d5_support_never_triggers_d5_itself`) updated to reflect that a web check now also fires for those records via D10. A committed fixture at `tests/fixtures/conflict-demo/` (3 vault notes + a citation-free draft repeating the planted false vote tally) exercises the source-conflict path end-to-end.

## What this supersedes

- **Decision 44** (Session 9): "Corpus route only for never-web claims this phase." Replaced by D2.
- **Phase 04 TG 04.4.2 milestone as specified** ("the 3 dataset-dependent claims receive corpus verdicts"): the Session 8 triage fix means the standard test file *correctly* contains no dataset-dependent claims, so that milestone is unsatisfiable as written. The Session 10 run verified everything else it was for: corpus wired end-to-end, hybrid search live, vault resolution, web verdicts, honest routing decisions. Phase 04 closes on that evidence; the live corpus-route exercise moves to this phase's milestone, which is strictly stronger (see below).
- `docs/playbook/claim-record-design.md` scope line for the corpus route (updated in TG 05.4).

## Quality gates carried forward (unchanged)

- Evidence evaluation at `high` tier on every route — never downgrade.
- Evidence summarization (mid tier) reused as-is; refuting-content preservation safeguards intact.
- Selection/disambiguation voting untouched.
- Conservative-up triage unchanged (D9 changes interpretation, not classification).
- Route-handler failures degrade to recorded reasons, never abort the run.
- Concurrency bounded (`Semaphore(5)`); corpus backend is self-hosted with a 3GB memory cap.

## Dependencies

- Phase 04 offline implementation (corpus client, route handler, CLI wiring) — complete, 400 tests green.
- Live corpus with the 3 ingested papers (`d_o3qBk5fESO_q` Nurullayev & Papa 2023, `d_7ZUo22uPGdsf` Kim 2023, `d_7lRaRsrtAJOW` de Carvalho 2025). **Zeng 2026 is not a blocker**: Zeng's ingestion (pending the doc-rag-backend null-byte fix, cross-repo note 2026-07-25) enriches the corpus when it lands; the milestone does not wait for it.
- OpenAI account topped up (Session 10) — either provider works for the milestone.

## Task Groups

Task breakdown within each TG is the implementing session's job. Implementation is delegated to sub-agents per the global model-routing table (Fable orchestrates; Sonnet for straightforward implementation, Opus for the cascade mechanism and cross-file work).

### TG 05.1: Cascade routing

**Goal:** `decide_route`/`execute_routing` support escalation: a claim whose routed tier returns a silent verdict is re-decided and may route to the next tier (vault-silent → corpus → web), within the same run.

**Success criteria:**
- General row candidates become `("corpus", "web")` — corpus preferred when declared, web fallback; never-web row remains `("corpus",)`.
- A silent verdict (per D6 normalization) triggers exactly one re-decision; a support/refute verdict ends the cascade (D5 confirmations excepted). No tier is attempted twice for the same claim (`_already_routed` semantics preserved).
- Policy table stays a readable, ordered list of self-describing rows; `decide_route` stays pure (normalization lookup is pure code).
- NARROW tests for every cascade path (vault-silent→corpus→support; →corpus-silent→web; never-web ends at corpus; no-corpus manifest degrades to today's behavior); MID regression green.

**Constraints:**
- Light profile (`run_from_pdf.py`) behavior byte-identical — no corpus, no cascade change observable.
- A manifest without `corpus_ids` must produce exactly today's routing (extensibility pillar in reverse: removal is a no-op).
- Escalation bounded: at most one handler invocation per tier per claim; total handler calls per claim ≤ 3.

### TG 05.2: Citation-aware corpus scoping

**Goal:** Corpus searches for cited claims are scoped to the documents their citations map to; citation-free claims search the declared corpus scope.

**Success criteria:**
- Cite-sets (wikilink and author-year forms) resolve to `document_ids` via the existing `map_citations_to_document_ids()`; ambiguous/unresolvable citations fall back to whole-scope search (conservative mapping semantics unchanged — ambiguous → dropped).
- Scoping recorded in the route verdict's provenance so the report shows *which documents* were searched.
- NARROW tests: scoped vs unscoped request shapes, unresolvable-citation fallback, provenance content.

**Constraints:**
- No server-side metadata search exists (recorded client need) — mapping stays client-side against `/documents`; do not hack around the gap.
- Mapping failures degrade to whole-scope search, never to route failure.

### TG 05.3: Importance-gated cross-checks (D4, D5)

**Goal:** Attribution checks for cited, corpus-mapped, importance ≥ 4 claims (even when vault-resolved); web confirmation for single-tier refutations of importance ≥ 4 web-eligible claims.

**Success criteria:**
- Vault-resolved cited claims with importance ≥ 4 and corpus-mapped citations receive a scoped corpus verdict alongside the vault verdict; vault-resolved citation-free claims are untouched.
- A single-tier refutation on an importance ≥ 4 web-eligible claim triggers exactly one web check; never-web refutations do not escalate and are annotated single-lineage (D8).
- Cost guardrail verified on the standard test file: total handler invocations under the new design stay within ~1.5× the Phase 03 baseline run (cross-checks are the exception, not the rule).
- NARROW tests for each gate combination (importance boundary, cited/uncited, mapped/unmapped, never-web exclusion).

**Constraints:**
- Supports never trigger routine cross-checks (D5) — guardrail against silently reintroducing web-checks-everything economics.
- Importance gate reads the existing triage field; no new LLM calls to decide gating.

### TG 05.4: Conflict detection, flags, and report

**Goal:** Pure normalization module (D6); `vault-corpus-check-needed` and `source-conflict` flags (D7); single-lineage annotation (D8); gap report renders all three; `claim-record-design.md` updated.

**Success criteria:**
- Normalization + conflict detection is a pure, LLM-free function with exhaustive NARROW tests over the verdict vocabulary (every enum value maps; unknown verdict values map to silent, never crash).
- `source-conflict` appears on the claim with both provenances side by side; `vault-corpus-check-needed` appears under Vault Improvement Signals; single-lineage resolutions are visibly annotated.
- `docs/playbook/claim-record-design.md` records the normalization table, both flags, and the superseded scope line.
- Gap report changes are additive — existing sections and light-profile rendering unchanged.

**Constraints:**
- Zero LLM calls in this TG's runtime code.
- Flag only clear support-vs-refute disagreements; silent/ambiguous never fires a flag (user decision — no noise from one-sided silence).

### TG 05.5: Milestone and wrap

**Goal:** Live heavy run on the standard test file proves the cascade end-to-end; docs aligned; Phase 04 formally closed.

**Success criteria:**
- **MILESTONE (FULL, live):** ~~heavy run on `workspace/inbox/ukraine-intro-test.txt` with vault + corpus (3 ingested docs) + web~~ **Superseded (Session 12):** the original 98-votes-on-real-corpus scenario was unreachable because (a) vault alignment against an author-year wikilink failed (note resolution was filename-only — fixed by `build_vault_index()` with alias support), and (b) the original D5 design prevented vault-supported claims from ever reaching web (the blind spot D10 closes). **Actual milestone (user-approved):** two complementary live runs:
  - **Cited-file run** (`workspace/inbox/ukraine-intro-cited-test.md` + real vault + live corpus): 16 claims, 8 vault / 4 corpus (citation-scoped search demonstrated) / 4 web. Cascade corpus→web demonstrated. ~2 min.
  - **Conflict-demo run** (`tests/fixtures/conflict-demo/` fixture vault, no corpus): 9 claims, planted "140 votes" error vault-supported → D10 web confirmation → web Refuted (real: 141) → `source-conflict` flag + REVISE-CLAIM in report. D10 gate demonstrated end-to-end.
- `docs/websearch-and-costs.md` updated (corpus cost profile, D10 impact, Session 12 data); CLAUDE.md, TASKS.md, HANDOVER.md current; pushed to origin.
- Phase 04 marked COMPLETE with a pointer to Phase 05; TG 04.4.2 recorded as superseded by this milestone.

**Constraints:**
- Live spend at the milestone only; full-paper runs remain post-phase and user-triggered.

## Phase success criteria

- A claim of any triage class can be verified against vault, corpus, and web in cost order, stopping when a sufficient tier resolves it — with no per-domain configuration beyond the manifest's declared resources. **Met:** cascade demonstrated live (Session 11 + Session 12 cited-file run).
- ~~The 98-votes case surfaces as `source-conflict` with both provenances — demonstrated live.~~ **Superseded (Session 12, user decision):** the original scenario was unreachable pre-D10 (vault-supported claims never reached web). D10 amendment opens the path; `source-conflict` demonstrated live via the conflict-demo fixture (planted "140 votes" error: vault support vs web refute). See Amendment (Session 12) section and TG 05.5.2b in TASKS.md for the full rationale.
- Removal test: a manifest with no corpus and no vault degrades to Phase 01 web-only behavior unchanged. **Met:** tested offline (test_orchestration.py).
- Offline suite green (400+ tests); light profile untouched. **Met:** 488 passed (488 non-slow), 3 deselected (slow).

## Risks and known failure modes

1. **Importance clustering blunts the gate.** In the Session 10 run, 12 of 16 claims scored importance ≥ 4 — the D4/D5 gate barely gates. Mitigation: D4/D5 are structurally narrow (cited-and-mapped; refutations only), so cost stays bounded even with a permissive gate. Observe the distribution at the milestone; if cross-check volume is high, recalibrating the triage prompt's importance guidance is a follow-up decision, not a silent tweak.
2. **Cascade latency adds a serial corpus stage** before web for unresolved claims. Corpus is the fast tier (no iteration loop), so expected wall-clock impact is small; measure at milestone.
3. **Whole-corpus search noise.** Citation-free claims searching a multi-document corpus may retrieve plausible-but-wrong passages. Mitigations already in place: high-tier evaluation, honest `corpus_insufficient`, summarization safeguards. Scoping (D3) removes this risk for cited claims.
4. **Double-lineage bookkeeping bugs** (same claim, verdicts from 3 tiers) could confuse `assign_suggested_actions`. Constraint: Phase 02's action-assignment semantics must be revisited deliberately in TG 05.4, not patched ad hoc — a claim with `source-conflict` outranks its individual verdicts for action purposes.
5. **Corpus availability flapping** (self-hosted backend down mid-run) must degrade per-claim to the next tier with a recorded reason, not abort — same rule as every route today.

## Implementation notes (Session 11 prep)

**VerificationResult enum gap:** `claim_verifier/schemas.py` only defines `SUPPORTED` and `REFUTED` (INSUFFICIENT_INFORMATION is commented out). The LLM prompt describes four values but schema constraint forces two. D6 normalization handles all strings defensively (unknown → silent). Web RouteVerdicts use `verdict.result.value` ("Supported"/"Refuted").

**Cascade architecture:** `execute_routing` becomes a multi-round loop (decide→dispatch→check-silent→re-decide). Vault runs BEFORE execute_routing in run_heavy.py, so cascade only handles corpus↔web escalation. Max 3 rounds per claim.

**D4/D5 are post-routing:** These bypass the policy table. `apply_cross_checks()` runs after `execute_routing`, before `assign_suggested_actions`. D4 uses the same scoped corpus handler from TG 05.2.

**Citation scoping approach:** Pre-fetch `list_documents()` once in run_heavy.py, pass to `make_corpus_route_handler(corpus_ids, documents=documents)`. Handler resolves `record.cite_set` per-claim via existing `map_citations_to_document_ids()`, intersects with declared `corpus_ids`.

## Lessons learned (Session 11)

1. **`load_vault()` appends `v-research` internally.** Pass the vault ROOT (e.g. `vault-main`), not the research subdirectory (`vault-main/v-research`). Passing the full path silently produces zero notes because it looks in `v-research/v-research/`. This caused the first two milestone runs to have no vault verdicts at all. No error is raised — vault stages silently no-op on empty vault.

2. **Vault `argument_pyramid` tags can change in the sibling repo.** The tag was renamed from `ukraine-vote` to `un-ukraine-russia-war-votes-working-paper` between sessions. The `--argument-pyramid` CLI value must match the current vault frontmatter exactly. A mismatch silently loads zero notes (same effect as passing the wrong path).

3. **Source-conflict requires a CITED claim that reaches both corpus and web.** The current test file (`ukraine-intro-test.txt`) has no wikilink citations, so D4 attribution checks never fire and no claim gets both corpus and web verdicts on the same claim. To demonstrate source-conflict live, create a test file with wikilink citations (e.g. `[[de Carvalho 2025]]`) whose citations map to corpus documents via `map_citations_to_document_ids()`. The 98-votes claim with a `[[de Carvalho 2025]]` citation would trigger D4 (vault-resolved + cited + importance >= 4 → scoped corpus check), producing corpus_supported (98) alongside vault_contradicted (93), which would fire `vault-corpus-check-needed`. Then D5 (refutation confirmation) would trigger web, producing web_refuted (93) → `source-conflict`.

4. **Cascade stop-on-support is correct but masks corpus errors.** When vault misses a claim and corpus supports the wrong value (e.g. 98), the cascade stops (D1). Web never runs, so the error goes undetected. **Partially mitigated by D10 (Session 12 amendment):** claims with importance ≥ 4 now get one web confirmation even when vault/corpus supports them. The blind spot remains for importance < 4 claims, where the fix is vault-matching quality rather than cascade policy.

## Roadmap after this phase

Phase 06 (Deep Research Commissions), Phase 07 (Draft Update Loop). The edge-case backlog carries forward; add: triage importance-distribution recalibration (Risk 1, sharpened by D10 — importance clusters ≥ 4 so support-confirmation fires broadly); zero-evidence web verdicts (VerificationResult enum gap); gap-report web-call counter undercounting D4/D5/D10 calls; vault-side aliases lint (SOURCE notes carrying "Author Year" aliases).
