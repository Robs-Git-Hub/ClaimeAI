# Claim Record Design

The multi-attribute claim record is the data contract for Phases 02–05. Each claim carries multiple attributes populated by different phases — not a single verdict label.

## Attribute Taxonomy

| Attribute | Type | Populated by | Description |
|-----------|------|-------------|-------------|
| `claim` | `Optional[ValidatedClaim]` | Phase 02/03 (TG 03.3 binder) | Claim identity from extraction (claim_text + provenance indices), present *before* any verification. The honest identity carrier for not-yet-web-verified records. |
| `web_verdict` | `Optional[Verdict]` | Phase 01 (web route) | Real web verification result; `None` until the web route runs (never fabricated to carry identity) |
| `citation_status` | `CitationStatus` | Phase 02 (TG 02.2) | Whether the claim has a parseable citation |
| `cite_set` | `List[str]` | Phase 02 (TG 02.2) | SOURCE note names from wikilink citations |
| `position` | `Optional[DraftPosition]` | Phase 02 (TG 02.2) | Location in the draft (section, offsets) |
| `route_verdicts` | `List[RouteVerdict]` | Phase 02 (TG 02.4/02.5) + Phase 03 (web/future routes) | Per-route verification results — renamed from `vault_verdicts` in TG 03.3 (the list was always route-generic; web verdicts accumulate here too) |
| `suggested_action` | `Optional[SuggestedAction]` | Phase 02 (TG 02.6) | What the author should do |
| `claim_strength` | `Optional[int]` | Phase 02 (TG 02.5) | Copied from matched vault CLAIM note (1–5) |
| `evidence_quality` | `Optional[int]` | Phase 02 (TG 02.5) | Copied from matched vault CLAIM note (1–5) |
| `triage_class` | `Optional[str]` | Phase 03 (TG 03.1) | Triviality / importance classification — see `TriageClass` below |
| `citation_expectation` | `Optional[str]` | Phase 03 (TG 03.1) | Whether academic citation is expected — see `CitationExpectation` below |
| `importance` | `Optional[int]` | Phase 03 (TG 03.1) | Importance score (1–5) — see `importance` semantics below |

## Enums

### CitationStatus

| Value | Meaning |
|-------|---------|
| `cited` | Claim has parseable wikilink citations |
| `citation_free` | No citation detected |
| `unparsed_citation` | Non-wikilink citation detected (e.g., plain author-year) but not bound |

### VaultVerdict

Route-specific verdicts for vault-based verification. Separate from `VerificationResult` (`Supported` / `Refuted` / `Insufficient Information` / `Conflicting Evidence`, Session 13) which is web-route-specific.

| Value | Route | Meaning |
|-------|-------|---------|
| `vault_supported` | aligned / matched | Vault evidence supports the claim |
| `vault_contradicted` | aligned / matched | Vault evidence contradicts the claim |
| `not_supported` | aligned | Cite exists but evidence doesn't back the claim (the miscite signal) |
| `note_not_in_vault` | aligned | Cited note not found in vault |
| `insufficient_vault_content` | aligned | Note exists but has no evidence children within one hop |
| `no_vault_match` | matched | No vault note matches; handed off to Phase 03 routing |

### SuggestedAction

| Value | When assigned |
|-------|-------------|
| `none` | Claim verified, no action needed |
| `fix_citation` | Miscite detected (not_supported verdict) |
| `add_citation` | Citation-free claim supported by vault — author should cite it |
| `add_vault_note` | Claim supported by web but not vault — vault improvement signal |
| `revise_claim` | Claim contradicted by evidence |
| `unresolved` | Insufficient evidence from all routes |

### TriageClass (Phase 03, TG 03.1)

Populated in one batch LLM call (`ingest/triage.py:triage_claims`, `mid` tier
or below — triage is the cost lever this phase spends on, never `high`) over
every claim in a draft, regardless of `citation_status`.

| Value | Meaning |
|-------|---------|
| `trivial` | Common knowledge; needs no verification. |
| `general-factual` | An ordinary factual claim a web search could verify. |
| `academic-citable` | The kind of claim a peer reviewer would expect an academic citation for. |
| `dataset-dependent` | Verifiable ONLY against the author's own private dataset or analysis outputs — NOT a fact of public record. |
| `novel-result` | The author's OWN, not-yet-published finding or result — new information that doesn't exist on the open web yet. |

`dataset-dependent` and `novel-result` exist specifically so TG 03.2's
routing policy can keep such claims away from web search: a web route can
only ever fail to find evidence for them, and a "Refuted" verdict on an
unpublished result is actively misleading (the Session 4 motivating failure
this phase exists to fix).

**`dataset-dependent`/`novel-result` are not a catch-all for "hard to
verify."** They exist only for facts genuinely unreachable by web search —
the author's own unpublished results, or figures that exist only in a
private dataset. They exclude anything a search engine could reach, however
specific-looking the figure: official vote tallies, published statistics,
government or intergovernmental-organization (IGO) records, and other facts
of public record are `general-factual` or `academic-citable`, never
`dataset-dependent`, and never `novel-result` if anyone other than the
author could also have reported them. (Motivating failure, Phase 03
milestone review: a UN General Assembly vote tally — an official public
record — was misclassified `dataset-dependent`, which skipped web
verification entirely and let a real error, "98 votes" for an actual 93,
go undetected. That is the worst-case outcome the vocabulary must now
prevent.)

### CitationExpectation (Phase 03, TG 03.1)

| Value | Meaning |
|-------|---------|
| `expected` | An academic citation would normally be expected here. |
| `not-expected` | No citation is normally expected (e.g. trivial claims, or the author's own novel result). |
| `optional` | A citation would strengthen the claim but isn't strictly required. |

### `importance` semantics (Phase 03, TG 03.1)

`importance` is an integer 1 (least load-bearing) to 5 (most load-bearing to
the draft's argument), clamped to that range by `triage_claims` regardless
of what the LLM returns. It is a Phase 03 field, populated independently of
Phase 02's `claim_strength` / `evidence_quality` (which come from a matched
vault CLAIM note's frontmatter) — triage never overwrites those two fields.

### Conservative-up rule (Phase 03, TG 03.1 and TG 03.2)

Uncertainty must degrade toward *more* verification, never toward
`trivial`. Concretely:

- The triage prompt instructs the model: when uncertain between `trivial`
  and any other class, choose the non-trivial class.
- The triage prompt also instructs a second, directional tie-break (added
  after the Phase 03 milestone review's UN vote-tally miscategorization):
  when uncertain between a never-web class (`dataset-dependent`,
  `novel-result`) and a web-verifiable class (`general-factual`,
  `academic-citable`), choose the web-verifiable class. Both directional
  rules push the same way — toward *more* verification, never less. As the
  user principle behind this states: it is better to send a little too much
  to web than too little, because a missed error is the worst-case outcome;
  cost is controlled by the `trivial`/never-web classes existing at all, not
  by leaning on them when uncertain.
- A claim the model omits from its batch response — or every claim, if the
  LLM call itself fails — is left with `triage_class`, `citation_expectation`,
  and `importance` all `None` (unclassified). `None` is never treated as
  `trivial` downstream; TG 03.2's routing policy treats an unclassified
  claim as needing full verification.
- A wrong "don't verify" is worse than a wasted verification call — this
  mirrors the same conservative bias already used by `evaluate_alignment`
  (defaults to `not_supported`) and `verify_matches` (defaults to
  `no_vault_match`) in Phase 02.

### RunProfile

| Value | Behavior |
|-------|---------|
| `light` | Phase 01 behavior: web verification only, no vault. For blogs and quick checks. |
| `heavy` | Full attribute set: vault verification + web. For academic drafts with vault. |

## Model Composition

`ClaimRecord` wraps `Verdict` (from `claim_verifier.schemas`) rather than replacing it. `Verdict` already duplicates `ValidatedClaim` fields (claim_text, disambiguated_sentence, original_sentence, original_index, result, reasoning, sources), so ClaimRecord does not re-duplicate them.

### Claim identity vs. web verdict (TG 03.3)

The heavy pipeline (`scripts/run_heavy.py`) builds records straight from Claimify `ValidatedClaim`s — *before* any web verification. Since a `Verdict` cannot exist without asserting a (Supported/Refuted) result, identity is carried by the `claim` field instead, and `web_verdict` stays `None` until the web route actually runs. No fake web result is ever fabricated to carry identity (a fabricated "Supported" would corrupt the report's `ADD_VAULT_NOTE` signal). Every stage reads claim text through the `claim_text` property, which prefers `claim` and falls back to `web_verdict` so Phase 01/02 records (where the verdict carried identity) keep working. The heavy binder is `ingest/citation_binder.py:bind_extracted_claims`.

### DraftPosition

Captures where a claim appears in the draft. `sentence_index` is available from extraction (mapped from `original_index`); section and character offsets are populated by TG 02.2 draft ingestion.

| Field | Type | Source |
|-------|------|--------|
| `section` | `Optional[str]` | TG 02.2 (section heading) |
| `section_index` | `Optional[int]` | TG 02.2 (0-based section number) |
| `sentence_index` | `int` | Extraction pipeline (`original_index`) |
| `char_start` | `Optional[int]` | TG 02.2 (character offset in draft) |
| `char_end` | `Optional[int]` | TG 02.2 (character offset in draft) |

### RouteVerdict

A verdict from a specific verification route, with provenance tracing back to the evidence.

| Field | Type | Description |
|-------|------|-------------|
| `route` | `str` | "web", "vault_aligned", "vault_matched" |
| `verdict` | `str` | Route-specific verdict value (from VaultVerdict or VerificationResult) |
| `reasoning` | `Optional[str]` | Explanation |
| `provenance` | `Optional[str]` | Note name, quote text, or URL |
| `provenance_type` | `Optional[str]` | "vault_note", "quote_note", "web_url" |

### ResourceManifest

Declares what evidence sources exist for a run. Code consults the manifest rather than assuming resources exist. Absence of a resource is a no-op, not an error.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `draft_path` | `Path` | required | Path to the draft being checked |
| `vault_path` | `Optional[Path]` | `None` | Path to Obsidian vault root |
| `argument_pyramid` | `Optional[str]` | `None` | Vault filter (frontmatter value) |
| `corpus_ids` | `Optional[List[str]]` | `None` | Phase 03: doc-rag-backend document IDs |
| `web_enabled` | `bool` | `True` | Whether web search is available |

## Design Invariants

1. **Existing schemas are untouched.** `Verdict`, `ValidatedClaim`, `VerificationResult`, `FactCheckReport` are not modified. ClaimRecord is additive.
2. **Phase 03 fields default to None.** The schema defines them now so later phases don't require schema migrations.
3. **Verdict *values* stay route-specific even though the list is shared.** `route_verdicts` (renamed from `vault_verdicts` in TG 03.3) holds `RouteVerdict`s from every route — web, `vault_aligned`, `vault_matched`, and future routes. Each carries its own `route` tag, verdict vocabulary (`VaultVerdict` vs `VerificationResult`), and provenance type; they are never conflated, they just share one list. Read claim identity via the `claim_text` property (prefers `claim`, falls back to `web_verdict`).
4. **Manifest absence = degraded, not broken.** A manifest without vault_path produces a vault-less run plan. No vault → no vault sections in the report, not empty ones.
5. **Positions from day one.** Every ClaimRecord has a DraftPosition even if only sentence_index is populated initially. Phase 05 depends on this.

---

## Routing Decisions (Phase 03, TG 03.2)

*Appended by the TG 03.2 session — see `ingest/routing.py` and
`project-management/phase-plans/phase-03-triage-and-routing.md`.*

Two new `ClaimRecord` fields, both `Optional[str]` defaulting to `None`:

| Field | Populated by | Description |
|-------|-------------|-------------|
| `routing_decision` | Phase 03 (TG 03.2) | The outcome of `decide_route`: `"resolved"`, `"skip-trivial"`, `"unverifiable-by-available-routes"`, or `"route-<name>"` (e.g. `"route-web"`) |
| `routing_reason` | Phase 03 (TG 03.2) | Human-readable explanation for the decision, for the audit trail in the gap report |

### RoutingDecision vocabulary

| Value | Meaning |
|-------|---------|
| `resolved` | The claim already has a `vault_supported` or `vault_contradicted` vault verdict; no further routing. |
| `skip-trivial` | `triage_class == "trivial"`; no verification needed. |
| `route-<name>` | The claim was routed to the named route (currently only `route-web`). |
| `unverifiable-by-available-routes` | No available route (per the manifest) could verify this claim — either none applies to its triage class (e.g. `novel-result`/`dataset-dependent` claims, until a Phase 04 corpus route exists), or the one route that could apply isn't declared in `manifest.available_routes`, or it was already attempted. |

### Policy table (`ingest/routing.py:POLICY`)

Evaluated top to bottom; first matching row wins. A generic
`RouteVerdict` (`route="web"` or any future route name) is appended to
`route_verdicts` when a route handler produces one — the list was renamed
from `vault_verdicts` in TG 03.3 because it was always route-generic
(`route: str`), not vault-only; see the field's own docstring.

| Row | Condition | Decision |
|-----|-----------|----------|
| vault-resolved | Claim already has a `vault_supported`/`vault_contradicted` verdict | `resolved` |
| trivial | `triage_class == "trivial"` | `skip-trivial` |
| never-web | `triage_class in {"novel-result", "dataset-dependent"}` | never `route-web`; falls to `unverifiable-by-available-routes` until a non-web route (Phase 04 corpus) is added to this row |
| general (catch-all) | `general-factual`, `academic-citable`, or unclassified (`None`) — ties break toward verifying | `route-web` if `"web"` is in `available_routes` and not already attempted, else `unverifiable-by-available-routes` |

### Extensibility contract

Adding a route (Phase 04 corpus RAG, a future specialist DB) is meant to
touch exactly two things:
1. `ROUTE_HANDLERS["<name>"] = <handler>` — register the handler.
2. Add `"<name>"` to the relevant `PolicyRow.candidate_routes` tuple (or
   add a new row).

Neither the orchestrator, the gap report, nor `ClaimRecord` should need
to change. This is proven by `tests/test_routing.py`'s extensibility
test, which registers a fake route with exactly this shape.

---

## Corpus Route (Phase 04, TG 04.3)

*Appended by the TG 04.3 session — see `ingest/corpus_route.py`,
`ingest/corpus_client.py` (TG 04.2.1), and
`project-management/phase-plans/phase-04-*.md`.*

`"corpus"` is now a real, registered verification route (previously
anticipated in the `never-web` policy row's comment). It verifies claims the
routing policy keeps away from web search (triage classes `novel-result`,
`dataset-dependent`) against the author's own ingested paper corpus
(doc-rag-backend, `https://api.ragtogo.com`), when the run's
`ResourceManifest.corpus_ids` is non-empty.

### CorpusVerdict

Route-specific verdicts for corpus-based verification. Separate from
`VaultVerdict` (vault-route-specific) and `VerificationResult`
(web-route-specific) — see `RouteVerdict.verdict`.

| Value | Meaning |
|-------|---------|
| `corpus_supported` | Corpus evidence clearly supports the claim. |
| `corpus_contradicted` | Corpus evidence clearly contradicts the claim. |
| `corpus_insufficient` | Corpus evidence was retrieved but doesn't address the claim closely enough to judge either way. |
| `no_corpus_hits` | The corpus search returned no chunks at all (recorded without an LLM call, mirroring `VaultVerdict.NOTE_NOT_IN_VAULT`/`INSUFFICIENT_VAULT_CONTENT` — "we looked and found nothing" is itself useful audit trail, distinct from "we couldn't look"). |

`RouteVerdict` for the corpus route: `route="corpus"`, `verdict=<CorpusVerdict
value>`, `reasoning=<from the route-local high-tier evaluation>`,
`provenance=<"document_id#chunk_id"` refs, comma-joined, one per matched
chunk, with section names appended when known`>`, `provenance_type=
"corpus_doc_id"`. `RouteVerdict.provenance_type`'s docstring now lists
`"corpus_doc_id"` alongside `"vault_note"`, `"quote_note"`, `"web_url"`.

### Pipeline

```
[claim routed to "corpus" (never-web triage class + corpus_ids available)]
  → search_corpus(claim_text, document_ids=corpus_ids)   (ingest/corpus_client.py)
      None (API down)         → handler returns None, no verdict, run continues
      no chunks               → RouteVerdict(verdict=no_corpus_hits), no LLM call
      chunks found            → wrap as Evidence(url="corpus://<doc_id>#<chunk_id>", ...)
  → summarize_evidence_for_claim (mid tier, config-gated, reused unmodified
    from claim_verifier/evidence_summarization.py — already evidence-source-agnostic)
  → route-local high-tier evaluation (ingest/corpus_route.py:_evaluate_corpus_evidence)
  → RouteVerdict(route="corpus", verdict=<corpus_supported|corpus_contradicted|corpus_insufficient>)
```

### Evaluation reuse decision

The corpus route does **not** call `claim_verifier.nodes.evaluate_evidence`.
At the time of this decision (Phase 04), that node's structured-output
verdict field, typed `claim_verifier.schemas.VerificationResult`, only
actually contained `Supported`/`Refuted` (`Insufficient Information` was
commented out of the enum even though the prompt text still described it)
— it could not represent the `corpus_insufficient` value this route's fixed
vocabulary requires. **Session 13** added `INSUFFICIENT`/`CONFLICTING`
members to `VerificationResult`, closing that gap for the web route — but
the corpus route's reasoning still holds: `corpus_supported` /
`corpus_contradicted` / `corpus_insufficient` / `no_corpus_hits` is its own
fixed vocabulary, distinct from web's `Supported` / `Refuted` /
`Insufficient Information` / `Conflicting Evidence`, and the corpus route's
provenance format (`document_id#chunk_id`) shares nothing with web's URL
provenance. Instead, `ingest/corpus_route.py` writes a small, route-local
high-tier evaluator following the house style of
`ingest/alignment.py:evaluate_alignment` (`get_llm(tier="high")` +
`with_structured_output`). Summarization is still reused unmodified from
`claim_verifier/evidence_summarization.py` and runs exactly once per claim,
before the route-local evaluation call — never twice.

### Manifest scoping

`RouteHandler` (the protocol in `ingest/routing.py`) is `async (record) ->
Optional[RouteVerdict]` — it has no way to receive `manifest.corpus_ids`
directly, and `execute_routing`'s signature is not changed to thread it
through. `ingest/corpus_route.py` exposes a **factory**,
`make_corpus_route_handler(corpus_ids)`, that closes over the document-id
scope and returns a `RouteHandler`. There is no module-level
`ROUTE_HANDLERS["corpus"]` entry (unlike `web_route_handler`) — a corpus
handler is meaningless without knowing which documents to search. The
orchestrator (TG 04.4, `scripts/run_heavy.py`) is expected to wire it as:

```python
from ingest.corpus_route import make_corpus_route_handler
from ingest.routing import ROUTE_HANDLERS, execute_routing

handlers = dict(ROUTE_HANDLERS)
if manifest.corpus_ids:
    handlers["corpus"] = make_corpus_route_handler(manifest.corpus_ids)
records = await execute_routing(records, manifest, handlers=handlers)
```

### Policy table update (Phase 04 → superseded by Phase 05)

The `never-web` row's `candidate_routes` changed from `()` to `("corpus",)`
in Phase 04. In Phase 05, the `general` (catch-all) row's
`candidate_routes` changed from `("web",)` to `("corpus", "web")` — corpus
is tried first when declared, web is fallback. This supersedes Decision 44
("corpus only for never-web").

---

## Three-Tier Evidence Cascade (Phase 05, TG 05.1–05.4)

*Appended by the TG 05.4 session — see `ingest/routing.py` (cascade,
normalization, cross-checks), `ingest/gap_report.py` (conflict detection,
flags), and `project-management/phase-plans/phase-05-*.md`.*

### Verdict normalization (D6)

Every route verdict maps to one of three normalized values. The function
`normalize_verdict()` in `ingest/routing.py` is the single source of truth.

| Verdict string | Normalized | Source |
|---|---|---|
| `vault_supported` | `support` | vault_aligned, vault_matched |
| `vault_contradicted` | `refute` | vault_aligned, vault_matched |
| `not_supported` | `silent` | vault_aligned |
| `no_vault_match` | `silent` | vault_matched |
| `note_not_in_vault` | `silent` | vault (gather_evidence) |
| `insufficient_vault_content` | `silent` | vault (gather_evidence) |
| `corpus_supported` | `support` | corpus |
| `corpus_contradicted` | `refute` | corpus |
| `corpus_insufficient` | `silent` | corpus |
| `no_corpus_hits` | `silent` | corpus |
| `Supported` | `support` | web |
| `Refuted` | `refute` | web |
| `Insufficient Information` | `silent` | web |
| `Conflicting Evidence` | `silent` | web |
| `handler_error` | `silent` | cascade infrastructure |
| (anything else) | `silent` | future-proofing |

**Session 13:** the web route's `VerificationResult` enum previously defined only `SUPPORTED`/`REFUTED` — `Insufficient Information`/`Conflicting Evidence` were described in the prompt but not representable, so empty evidence, an LLM failure, or an unparseable verdict all fell through a `ValueError` fallback to `REFUTED`. The enum now has `INSUFFICIENT`/`CONFLICTING` members and the web route actually emits them. The normalization table above already treated both strings as `silent`; `normalize_verdict()` itself needed no change.

### Cascade routing (D1)

`execute_routing()` runs a multi-round cascade: after concurrent handler
dispatch, records with silent verdicts are re-decided via `decide_route()`
(the already-routed check skips the just-attempted tier automatically). Max
3 rounds. The general row's `candidate_routes=("corpus", "web")` means
corpus is tried first; web is fallback on silent.

### Citation-aware corpus scoping (D3)

`make_corpus_route_handler(corpus_ids, documents=documents)` resolves
`record.cite_set` per-claim via `map_citations_to_document_ids()`,
intersects with declared `corpus_ids`. Empty intersection → whole-scope
fallback. Scoped searches use `provenance_type="corpus_cited_doc"`.

### Cross-checks (D4, D5)

`apply_cross_checks()` runs after `execute_routing()`, before action
assignment. Two gates:

| Gate | Condition | Action |
|------|-----------|--------|
| D4 (attribution) | vault-resolved + cited + importance ≥ 4 + corpus not yet routed | Scoped corpus check alongside vault verdict |
| D5 (refutation confirmation) | single-tier refute + importance ≥ 4 + web-eligible + web not yet routed | One web check for independent confirmation |
| D10 (support confirmation, Amendment Session 12) | support verdict (vault or corpus) + importance ≥ 4 + web-eligible + web not yet routed | One web check for independent confirmation |

Supports never trigger cross-checks via D5 (cost guardrail) — but D10 (Session 12 amendment) now fires a web confirmation for importance ≥ 4 supports specifically, superseding that guardrail for important claims. Config-switchable via `pipeline.support_confirmation` in `config.toml` (default on).

### Conflict flags (D7)

`detect_conflicts()` in `ingest/gap_report.py` is pure, LLM-free. Two flags:

| Flag | Fires when | Report location |
|------|-----------|----------------|
| `source-conflict` | Shared-lineage (vault/corpus) and web disagree (support vs refute) | Per-claim detail, both provenances side by side |
| `vault-corpus-check-needed` | Vault and corpus disagree (support vs refute) | Vault Improvement Signals section |

Silent or unknown verdicts never trigger flags.

### ClaimRecord additions

| Field | Type | Default | Populated by |
|-------|------|---------|-------------|
| `conflict_flags` | `List[str]` | `[]` | Phase 05 (TG 05.4, `detect_conflicts()`) |

### Single-lineage annotation (D8)

Derived at report render time (no stored field). A claim whose only verdicts
come from shared lineage (vault/corpus routes) and has no independent (web)
check is annotated "(single-lineage)" in the report. Not applied to trivial
or unverifiable claims.

### Lineage groups

| Group | Routes |
|-------|--------|
| Shared | `vault_aligned`, `vault_matched`, `corpus` |
| Independent | `web` |

Vault and corpus share one lineage (vault derived from corpus sources).
Cross-checks (D5) use web, never vault↔corpus — confirming one against the
other is circular (the 98-votes case proved this in practice).

### `assign_suggested_actions` priority update

`source-conflict` in `conflict_flags` → `REVISE_CLAIM` as top priority,
before vault_contradicted. A source-conflict outranks individual verdicts.
