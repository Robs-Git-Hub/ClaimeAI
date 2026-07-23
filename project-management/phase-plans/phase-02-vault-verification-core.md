# Phase 02: Vault Verification Core

**Status:** PLANNED
**Goal:** Verify a markdown draft with wikilink citations against its trusted Obsidian vault — the best-case scenario for academic claim verification. Produce a gap report that tells the author what is supported, what is miscited, and where the vault is thin.

---

## Context

### The problem this phase solves

Phase 01 verifies claims against web search. That works for general factual claims but not for academic writing, where claims must be verified against the literature. Session 4 design discussion (2026-07-23) established the full problem space and a best-case-first strategy: build the happy path end-to-end, then add edge cases (missing vault, PDF-only drafts, absent sources) as later phases.

The best case: the author's draft is markdown, its citations are wikilinks to vault SOURCE notes, and the vault is trusted. This is exactly the state of the ukraine-vote-analysis working paper, which is the test corpus for this phase.

### Two verification modes

- **Cited claims** — *alignment verification*: does the cited source actually say what the claim says it says? Ground truth is the source's QUOTE notes in the vault, not the world.
- **Citation-free claims** — *truth verification*: match the claim against the vault's note corpus. (Web/corpus/deep-research routing for claims that miss the vault is Phase 03.)

### Design pillars (agreed Session 4 — do not re-litigate)

1. **Claim record, not claim verdict.** Each claim carries multiple attributes (citation status, verdicts per route, provenance, suggested action, draft position) — not a single label. The schema defines attributes that later phases populate (e.g. triage classes) even where Phase 02 leaves them empty.
2. **Run profiles.** `light` = Phase 01 behavior (web verdicts only) for blogs/quick checks; `heavy` = full attribute set with vault verification. Chosen at invocation.
3. **Resource manifest.** Every run starts from a declaration of what evidence sources exist for *this* document (draft path, vault path, corpus ids, web). Code consults the manifest rather than assuming resources exist. Phase 02 only implements the vault-present path, but absence must be a no-op, not an error — this is what makes later edge-case phases additive instead of rewrites.
4. **The vault is trusted.** A vault match is a verdict. No quote-vs-original re-verification, no vault QA in this tool. (Vault-side chain-completeness checking — the old Phase 02 concept — is deferred to the backlog as a separate capability.)
5. **Wikilink citations only.** Plain-text author-year parsing is a future input adapter. A minimal detector may flag non-wikilink citations as "unparsed citation" but must not attempt binding.
6. **Cite sets with union semantics.** A claim decomposed from a multi-cite sentence inherits the *set* of citations; it is supported if any cited source supports it. No attempt to resolve which cite the author intended for which claim.
7. **Positions from day one.** Every claim carries its location in the draft (section, character/sentence offsets) from extraction onward. Phase 05 (draft update loop) depends on this; retrofitting is expensive.
8. **Batch vault matching.** One large-context call proposing claim↔note matches (all claims + serialized vault), then a per-match verification pass. Never per-claim vault searches — cost must scale with vault size, not claim count.

### The test corpus

`../ukraine-vote-analysis/` (sibling repo, cloned locally):

- Vault at `vault-main/`; 421 research notes in `v-research/`; schema at `vault-main/_index/property-enums.md` and `v-research/DESIGN-argument-pyramid-note-type-architecture.md`.
- Note taxonomy: SOURCE (148), QUOTE (42), PARA (10), CLAIM (18), THESIS (14), OBS (10), RESULT (13), HYP (60), INT (6), plus non-evidence types (DESIGN, EXP, MOC, MS, …).
- Evidence chains via wikilinks: CLAIM → PARA → QUOTE → SOURCE (literature lane); CLAIM → INT → RESULT → EXP (empirical lane). QUOTE notes carry `source:` citation + `location:` (page); SOURCE notes carry full citation, DOI, `source_url`, and a "Quotes extracted" wikilink list.
- `argument_pyramid: [paper-name]` frontmatter marks notes belonging to a specific paper — use it to pre-filter the vault per run.
- CLAIM notes carry `claim_strength` and `evidence_quality` (1–5) — read these where a draft claim matches a vault CLAIM note; do not invent importance scores in this phase.
- The draft: `vault-main/v-research/MS-DRAFT-working-paper-ukraine-vote-analysis-v2-full-text.md` (~7,000 words), citations as `[[SOURCE-…|Author (Year)]]` wikilinks.

### Scale and cost expectations

Serialized vault (frontmatter + key sections) ≈ 100–150K tokens for 421 notes; `argument_pyramid` filtering reduces this substantially. The batch-match call is the expensive step — the broad pass may use a cheaper large-context model; the per-match verify pass uses the `high` tier, consistent with the pipeline's existing cheap-broad-then-careful-verify pattern.

## Dependencies

- Phase 01 pipeline (complete): claim extraction, `get_llm()` tier registry, config.toml conventions.
- `ukraine-vote-analysis` repo cloned as a sibling directory (read-only — this tool must never write to the vault).
- No new API accounts needed; heavy runs spend LLM credit (batch call + verify passes).

## Task Groups

### TG 02.1: Claim Record, Run Profiles, Resource Manifest

**Goal:** The data model that everything else builds on: a multi-attribute claim record, `light`/`heavy` run profiles, and a per-run resource manifest.

**Success criteria:**
- Pydantic models for the claim record (citation status, cite set, draft position, per-route verdicts with provenance, suggested action; placeholder fields for Phase 03 triage attributes).
- A manifest model + loader (draft path, optional vault path, optional corpus ids, web flag); a manifest without a vault validates and produces a vault-less run plan.
- A light-profile run on Phase 01's test input produces results equivalent to Phase 01 (regression: existing behavior unchanged).
- Offline tests for models, manifest validation, and profile selection.

**Constraints:**
- Follow existing conventions: config.toml for defaults, Pydantic settings overrides, no model names outside the registry.
- Do not break the three existing LangGraph graphs or the 87 existing offline tests.

**Context:** The record schema is the contract for Phases 03–05 — a short design doc in `docs/playbook/` recording attribute taxonomies (and which phase populates each) is part of the deliverable.

### TG 02.2: Draft Ingestion and Citation Binding

**Goal:** Parse a wikilinked markdown draft into claims that carry their positions and their cite sets.

**Success criteria:**
- Given the ukraine draft, produces claims with: section, position offsets, citation status (cited / citation-free), and for cited claims the set of SOURCE note names from wikilinks.
- Multi-cite sentences yield claims bound to the full cite set (union semantics).
- A stated, tested heuristic for paragraph-trailing citation scope (how far back a trailing cite reaches) — the choice is the implementer's, but it must be documented and encoded in tests.
- Non-wikilink citation patterns (plain author-year) are flagged `unparsed-citation`, not bound.

**Constraints:**
- Reuse the Phase 01 extraction pipeline (Claimify selection/disambiguation/decomposition with its voting gates) rather than building a parallel extractor; citation markers must survive or be re-attached through decomposition so binding isn't lost.
- Positions must survive the whole pipeline — this is the Phase 05 enabler (design pillar 7).

**Context:** Wikilink syntax in the draft: `[[SOURCE-slug|Display (Year)]]`. Claims and citations are many-to-many at sentence level; treat paragraph-level trailing cites conservatively (a wrong "citation-free" beats a wrong binding — the former triggers verification, the latter fabricates support).

### TG 02.3: Vault Serializer

**Goal:** Turn a vault into the JSON evidence corpus the matching stage consumes.

**Success criteria:**
- Serializes vault notes to JSON: note name, type, frontmatter, key body sections, outgoing wikilinks.
- Filters by `argument_pyramid` value and by note type (evidence types in; DESIGN/EXP/MOC/MS and other non-evidence types out).
- Reports token-count of the serialized output; warns when it exceeds a configurable budget.
- Tested against fixture notes AND validated against the real ukraine vault (421 notes parse without error; spot-check counts per type match the exploration report).

**Constraints:**
- Read-only against the vault — never write, never move.
- Tolerate schema drift: notes with missing/extra frontmatter fields must degrade gracefully (skip fields, don't crash), since the vault predates this tool.

**Context:** Vault schema documented in `_index/property-enums.md` and `DESIGN-argument-pyramid-note-type-architecture.md` — read both before designing the serialization.

### TG 02.4: Cited-Claim Alignment

**Goal:** For each cited claim whose SOURCE notes are in the vault: does the cited source support the claim?

**Success criteria:**
- For each (claim, cite set): resolve SOURCE notes → their QUOTE (and PARA) notes → evaluate whether the quoted material supports the claim.
- Verdicts: `supported` (with the supporting QUOTE note as provenance), `not-supported` (cite exists but quotes don't back the claim — the miscite signal), `source-not-in-vault` (flagged, not verified — no PDF fetching in this phase).
- Union semantics: supported by any source in the cite set = supported.
- Evaluated with the `high` tier; offline tests with fixture notes plus a live spot-check on real draft claims.

**Constraints:**
- Never downgrade alignment evaluation below the `high` tier (same rule as Phase 01 evidence evaluation).
- A SOURCE note with no extracted QUOTE notes is `insufficient-vault-content`, distinct from `source-not-in-vault` — both are vault-improvement signals, don't conflate them.

**Context:** This is the mechanically simpler mode — the evidence chain is navigable via wikilinks, no matching needed. Alignment failures are the highest-value finding for an author (a miscite survives peer review worse than a missing cite).

### TG 02.5: Citation-Free Vault Matching

**Goal:** Match citation-free claims against the vault in bulk, then verify the proposed matches.

**Success criteria:**
- Stage 1 (batch match): one call over all citation-free claims + serialized vault proposes candidate claim↔note matches. Cost scales with vault size, not claim count.
- Stage 2 (verify): each proposed match is independently evaluated at the `high` tier; verdicts `vault-supported` (provenance = note), `vault-contradicted`, or `no-vault-match`.
- `no-vault-match` claims are cleanly handed off as the Phase 03 routing input (in Phase 02 they simply appear in the report as unresolved).
- Where a claim matches a vault CLAIM note, `claim_strength`/`evidence_quality` are copied onto the claim record.
- Offline tests with a fixture vault; live validation against the ukraine vault.

**Constraints:**
- The batch pass may use a cheaper large-context model; the verify pass must not drop below `high` (broad-cheap-then-verify, the established pipeline pattern).
- False negatives in the batch pass are acceptable (claim shows as unresolved → Phase 03 catches it); false positives must die in the verify pass — tune prompts accordingly.

**Context:** This implements the user's batching insight: an article with 1,000 claims must not trigger 1,000 vault searches. Match quality depends on the serializer's choices (TG 02.3) — expect iteration between these two TGs.

### TG 02.6: Gap Report v2

**Goal:** A report the author can act on, organized around what to *do*, not just what was found.

**Success criteria:**
- Per-claim: all populated attributes, verdicts with provenance (which note, which quote), and a suggested action from a small fixed vocabulary (e.g. `none`, `fix-citation`, `add-citation`, `add-vault-note`, `revise-claim`, `unresolved`).
- Report sections adapt to the manifest: no vault declared → no vault sections (not empty ones).
- The vault-improvement signal is explicit: claims supported only outside the vault, cited sources with no quotes, sources not in the vault.
- Machine-readable results.json (the full claim records) + human report.md, extending the Phase 01 output convention in `workspace/output/<stem>/`.

**Constraints:**
- Every verdict in the report must be traceable to provenance — no naked "supported."
- Keep the light-profile report backward compatible with Phase 01's format.

**Context:** The report is doing double duty: verifying the article *and* telling the author where the vault is thin (the writing-process feedback loop). Design for the reader who will fix the draft, not for a scorecard.

### TG 02.7: Quality & Wrap

**Goal:** Prove the phase deliverable end-to-end and leave the project in a handover-clean state.

**Success criteria:**
- **The phase milestone:** a heavy run over the ukraine working paper completes and produces a gap report the user judges useful (user review is the acceptance gate).
- A light run on a non-vault document still behaves like Phase 01 (regression).
- Offline test suite green; docs updated (CLAUDE.md pipeline/conventions, docs/ as needed); TASKS.md and HANDOVER.md current; pushed to origin.

**Constraints:**
- Live runs spend API credit — reserve them for TG milestones; everything else verifies offline (established Phase 01 discipline).
- Run `docs-align-check` before wrap.

## Success Criteria (phase)

- A heavy run over `MS-DRAFT-working-paper-ukraine-vote-analysis-v2-full-text.md` with the ukraine vault produces a gap report covering: cited-claim alignment verdicts, citation-free vault matches, miscite flags, and vault-improvement signals — judged useful by the user.
- Light profile reproduces Phase 01 behavior on non-academic input.
- A manifest without a vault runs without error (degraded, not broken).
- Claim records carry draft positions end-to-end.

## Risks and known failure modes

- **Citation markers lost in decomposition.** The Claimify stages rewrite sentences; if wikilinks are stripped before binding, cited claims silently become citation-free. Bind citations before or alongside decomposition, and test for survival.
- **Batch-match context overflow.** A large vault + long draft may exceed the matching model's context. The serializer's token accounting and `argument_pyramid` filtering are the mitigations; chunked matching is the fallback (accepting some cross-chunk match loss).
- **Vault schema drift.** The vault is a living research artifact; notes will not all match the documented schema. Serializer must degrade per-note, never abort the run.
- **Over-claiming matches.** A plausible-but-wrong vault match is worse than no match (it fabricates support). The verify pass exists to kill these; keep it adversarial.

## Roadmap (Phases 03–05 and backlog)

| Phase | Contents |
|---|---|
| **03 — Routing & corpus** | Triage classifier (triviality, citation-expectation, importance), web route reuse, doc-rag-backend client (`GET /search` on api.ragtogo.com, corpus scoped by `document_ids` in the manifest), routing policy for `no-vault-match` claims |
| **04 — Deep research commissions** | Escalation candidate selection (human-approved), commission document writer, response-paper ingestion and re-evaluation |
| **05 — Draft update loop** | Propose draft edits (insert citations) after vault improvement; the "would a peer reviewer ask for evidence?" test as trigger |

**Edge-case backlog** (each a future input adapter or route, enabled by the manifest + claim record design):

- PDF-only drafts / plain-text author-year citation parsing and binding
- Source fetching for cited-but-absent papers
- Vault-less heavy runs (corpus/web-only academic verification)
- Vault QA / argument-chain completeness checking (the original Phase 02 concept, deferred when the vault was declared trusted)
- Semi-automated vault enrichment from gap report signals
