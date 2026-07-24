# Instructions for Claude

## Project Overview

A fork of [BharathxD/ClaimeAI](https://github.com/BharathxD/ClaimeAI) — an automated fact-checking system that extracts factual claims from text and verifies each one against web evidence. Built on LangGraph with a three-stage pipeline: claim extraction (Claimify methodology), claim verification (SAFE-inspired), and orchestration.

This fork strips the original to the agent backend only (no web frontend, no Chrome extension) and adds PDF ingestion, OpenRouter support, and a Claude Code `/claimify` skill for CLI-driven fact-checking.

### Upstream

- **Original repo:** `https://github.com/BharathxD/ClaimeAI`
- **Remote:** `upstream` (fetch only, push blocked — see `HOWTO-safely-fork-others-repos` in control hub vault)
- **Do not push to upstream.** All work goes to `origin` (Robs-Git-Hub/ClaimeAI).

### Directory Layout

| Directory          | Purpose                                              |
| ------------------ | ---------------------------------------------------- |
| `claim_extractor/` | Stage 1 — extract claims from text (Claimify method) |
| `claim_verifier/`  | Stage 2 — verify claims via web search               |
| `fact_checker/`    | Stage 3 — orchestrator, dispatches parallel verification |
| `utils/`           | Shared utilities (LLM, Redis, settings)              |
| `ingest/`          | Stage 0 — PDF/text ingestion (Docling), chunking     |
| `security/`        | API key auth for LangGraph                           |
| `scripts/`         | CLI dev tools and runners                            |
| `workspace/`       | Working directory: `inbox/` (inputs), `output/` (results) |
| `docs/`            | Project documentation                                |
| `project-management/` | Phase plans and task tracker                      |

### Key Files

- `config.toml` — non-sensitive pipeline config (provider, models, search settings, reasoning effort). Env vars override via Pydantic.
- `.env` — secrets only (API keys, Redis URI)
- `langgraph.json` — graph registry for LangGraph CLI
- `pyproject.toml` — Python dependencies (Poetry)
- `utils/config.py` — loads `config.toml` with `tomllib`
- `utils/settings.py` — env var validation (Pydantic); `llm_provider` default comes from `config.toml`
- `utils/models.py` — `get_llm()` factory; `MODEL_REGISTRY` and `REASONING_CONFIG` loaded from `config.toml`
- `utils/cost_tracking.py` — search cost counter (process-local, INFO logging)
- `claim_extractor/llm/config.py` — extraction temperature constants (models live in the registry)
- `claim_verifier/llm/config.py` — verification temperature constants (models live in the registry)
- `ingest/pdf.py` — PDF-to-markdown extraction via Docling (lazy import)
- `ingest/chunking.py` — heading-based text chunking (H1/H2, code-fence aware)
- `ingest/draft_types.py` — shared types for draft parsing (WikilinkCitation, ParsedSentence, ParsedDraft)
- `ingest/draft_parser.py` — wikilink parsing, author-year detection, sentence splitting, `parse_draft()`
- `ingest/citation_binder.py` — maps pipeline Verdicts to ClaimRecords via `original_index`
- `ingest/vault_serializer.py` — parses Obsidian vault notes, filters by argument_pyramid/type, serializes to JSON with token counting
- `utils/claim_record.py` — ClaimRecord (Phase 02–05 data contract), CitationStatus, VaultVerdict, SuggestedAction, DraftPosition, RouteVerdict
- `utils/run_config.py` — ResourceManifest (declares evidence sources per run), RunProfile (light/heavy)
- `ingest/alignment.py` — cited-claim alignment: `gather_evidence()` (one-hop vault traversal) + `evaluate_alignment()` (high-tier LLM evaluation)
- `ingest/vault_match.py` — citation-free vault matching: `batch_match_claims()` (mid-tier batch proposal) + `verify_matches()` (high-tier adversarial verification)
- `ingest/triage.py` — batch triage classifier: `triage_claims()` populates `triage_class`, `citation_expectation`, `importance` on all claims in one mid-tier call
- `ingest/routing.py` — routing policy + route-handler registry: `decide_route()` (pure function, policy table), `execute_routing()` (dispatches to handlers), extensible for Phase 04+
- `ingest/gap_report.py` — gap report rendering: `assign_suggested_actions()`, `render_gap_report()`, `serialize_results()`
- `claim_verifier/evidence_summarization.py` — evidence summarization: `summarize_evidence_for_claim()` condenses raw search results at mid tier before high-tier evaluation
- `scripts/run_from_pdf.py` — CLI entry point for PDF/text/markdown fact-checking (light profile)
- `scripts/run_heavy.py` — CLI entry point for heavy-profile runs: draft + vault → parse → extract → bind → vault verify → triage → route → gap report
- `scripts/spot_check_vault.py` — live spot-check script for alignment + vault matching against real vault
- `docs/playbook/claim-record-design.md` — attribute taxonomy and phase ownership for ClaimRecord
- `docs/llm-providers.md` — tier × provider model mapping table
- `docs/websearch-and-costs.md` — Exa/Tavily and LLM cost estimates

## Pipeline

### Web verification (Phase 01 — light profile)

```
Text → Sentence Split (NLTK) → Selection (voting) → Disambiguation (voting)
     → Decomposition → Validation → [claims]
     → Generate Search Query → Web Search (Exa/Tavily) → Evaluate Evidence
     → Verdict: Supported | Refuted | Insufficient | Conflicting
```

### Vault verification (Phase 02 — heavy profile, requires Obsidian vault)

```
Draft (markdown with wikilinks) → parse_draft() → bind_citations() → [ClaimRecords]
  Cited claims:    → gather_evidence(note + one-hop links) → evaluate_alignment (high tier)
                   → Verdict: vault_supported | vault_contradicted | not_supported
  Citation-free:   → batch_match_claims (mid tier, one call) → verify_matches (high tier)
                   → Verdict: vault_supported | vault_contradicted | no_vault_match
  All claims:      → assign_suggested_actions() → render_gap_report()
```

### Triage & Routing (Phase 03 — heavy profile, after vault verification)

```
[ClaimRecords with vault verdicts]
  → triage_claims (mid tier, one batch call) → [triage_class, citation_expectation, importance]
  → decide_route (pure function, policy table):
      vault-resolved (supported/contradicted) → no further routing
      trivial                                 → skip
      novel-result / dataset-dependent        → never web (unverifiable until corpus route)
      general-factual / academic-citable / unclassified → route to web
  → web route: search → summarize_evidence (mid tier) → evaluate_evidence (high tier)
  → render_gap_report() with triage, routing decisions, route summary
```

Full-vault fallback: claims unmatched by the paper-scoped batch pass get one additional high-tier batch call against the full vault (evidence types only, no argument_pyramid filter). Matches from the fallback are flagged as "consider adding argument_pyramid tag" in the gap report.

### Quality gates

- Selection and disambiguation use 3 LLM completions with 2/3 majority voting. Do not reduce this — it is the primary quality mechanism.
- Evidence evaluation (web and vault) uses the "high" tier (GPT-4.1 — OpenAI's smartest non-reasoning model, or Claude Sonnet 5 — Anthropic's frontier hybrid-reasoning model with selectable effort levels). Never downgrade this tier. See `docs/playbook/model-tier-selection.md` for rationale.
- Vault batch matching: pass 1 (paper-scoped) uses "mid" tier; pass 2 (full-vault fallback) uses "high" tier. Each proposed match is re-verified at "high" tier adversarially. Batch-match prompts seek contradictions as well as confirmations.
- Evidence summarization (mid tier) condenses raw search results before high-tier evaluation, preserving refuting content and URL attribution. Config-switchable (`summarize_evidence` in config.toml, default on).
- Triage is conservative-up: unclassified claims route to web (never default to trivial); uncertain between never-web and web-verifiable → choose web-verifiable.
- Up to 5 search iterations per claim if evidence is insufficient (web route only).

## Running

```bash
# Install
poetry install

# Start LangGraph dev server (--allow-blocking needed for NLTK's sync tokenizer)
poetry run dev
# Or manually: langgraph dev --no-browser --allow-blocking

# Run fact-checker on a PDF, markdown, or text file
python scripts/run_from_pdf.py <path>

# Run fact-checker on inline text (legacy)
python scripts/run_fact_checker.py
```

### Required env vars

```
OPENAI_API_KEY=sk-proj-...
EXA_API_KEY=...
REDIS_URI=redis://localhost:6379
```

Optional: `TAVILY_API_KEY`, `LANGSMITH_API_KEY`, `OPENROUTER_API_KEY` (`sk-or-...`, required when `llm_provider=openrouter` in config.toml)

## Conventions

- All LLM calls go through `utils/models.py:get_llm()` — nodes pass a `tier` (`low`, `mid`, `high`) and the registry resolves the model for the active provider (OpenAI via `init_chat_model`, OpenRouter via `ChatOpenAI` against `https://openrouter.ai/api/v1`)
- Non-sensitive config in `config.toml` (provider, models, search settings); secrets in `.env`; env vars override config.toml
- Structured output via `llm.with_structured_output(PydanticModel)` everywhere
- Voting via `utils/llm.py:process_with_voting()` — N completions, M required successes
- Search provider configured in `config.toml` `[pipeline]` section (default: `exa`)
