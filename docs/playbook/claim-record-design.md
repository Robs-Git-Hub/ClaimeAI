# Claim Record Design

The multi-attribute claim record is the data contract for Phases 02–05. Each claim carries multiple attributes populated by different phases — not a single verdict label.

## Attribute Taxonomy

| Attribute | Type | Populated by | Description |
|-----------|------|-------------|-------------|
| `web_verdict` | `Optional[Verdict]` | Phase 01 (web route) | Existing Phase 01 verification result |
| `citation_status` | `CitationStatus` | Phase 02 (TG 02.2) | Whether the claim has a parseable citation |
| `cite_set` | `List[str]` | Phase 02 (TG 02.2) | SOURCE note names from wikilink citations |
| `position` | `Optional[DraftPosition]` | Phase 02 (TG 02.2) | Location in the draft (section, offsets) |
| `vault_verdicts` | `List[RouteVerdict]` | Phase 02 (TG 02.4/02.5) | Per-route vault verification results |
| `suggested_action` | `Optional[SuggestedAction]` | Phase 02 (TG 02.6) | What the author should do |
| `claim_strength` | `Optional[int]` | Phase 02 (TG 02.5) | Copied from matched vault CLAIM note (1–5) |
| `evidence_quality` | `Optional[int]` | Phase 02 (TG 02.5) | Copied from matched vault CLAIM note (1–5) |
| `triage_class` | `Optional[str]` | Phase 03 | Triviality / importance classification |
| `citation_expectation` | `Optional[str]` | Phase 03 | Whether academic citation is expected |
| `importance` | `Optional[int]` | Phase 03 | Importance score (1–5) |

## Enums

### CitationStatus

| Value | Meaning |
|-------|---------|
| `cited` | Claim has parseable wikilink citations |
| `citation_free` | No citation detected |
| `unparsed_citation` | Non-wikilink citation detected (e.g., plain author-year) but not bound |

### VaultVerdict

Route-specific verdicts for vault-based verification. Separate from `VerificationResult` (Supported/Refuted) which is web-route-specific.

| Value | Route | Meaning |
|-------|-------|---------|
| `vault_supported` | aligned / matched | Vault evidence supports the claim |
| `vault_contradicted` | aligned / matched | Vault evidence contradicts the claim |
| `not_supported` | aligned | Cite exists but quotes don't back the claim (the miscite signal) |
| `source_not_in_vault` | aligned | Cited SOURCE note not found in vault |
| `insufficient_vault_content` | aligned | SOURCE exists but has no extracted QUOTE notes |
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

### RunProfile

| Value | Behavior |
|-------|---------|
| `light` | Phase 01 behavior: web verification only, no vault. For blogs and quick checks. |
| `heavy` | Full attribute set: vault verification + web. For academic drafts with vault. |

## Model Composition

`ClaimRecord` wraps `Verdict` (from `claim_verifier.schemas`) rather than replacing it. `Verdict` already duplicates `ValidatedClaim` fields (claim_text, disambiguated_sentence, original_sentence, original_index, result, reasoning, sources), so ClaimRecord does not re-duplicate them.

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
3. **Vault verdicts are separate from web verdicts.** Different enum, different semantics, different provenance types. Never conflated.
4. **Manifest absence = degraded, not broken.** A manifest without vault_path produces a vault-less run plan. No vault → no vault sections in the report, not empty ones.
5. **Positions from day one.** Every ClaimRecord has a DraftPosition even if only sentence_index is populated initially. Phase 05 depends on this.
