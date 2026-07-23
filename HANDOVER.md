# Session Handover

**Last Updated:** 2026-07-23 (Session 6, outgoing)
**Current Status:** Phase 02 IN PROGRESS — TGs 02.1–02.3 complete, TGs 02.4–02.7 remaining.

---

## Start Here

**Outgoing session completed:** TGs 02.1–02.3 of Phase 02 (data models, draft parsing/citation binding, vault serializer). 107 new tests, all green. No pipeline code was modified — all new files are additive.

**Incoming session should:**

1. **Begin TG 02.4 (Cited-Claim Alignment).** This is the first LLM-calling stage: for each cited claim, resolve its SOURCE notes → QUOTE/PARA notes → evaluate whether the quoted material supports the claim. Uses the `high` tier. See `project-management/phase-plans/phase-02-vault-verification-core.md` TG 02.4 for spec.

2. **Key integration context for TG 02.4:**
   - `ingest/vault_serializer.py` provides `load_vault()` and `parse_vault_note()` — read vault notes, filter by argument_pyramid/type
   - `ingest/citation_binder.py` provides `bind_citations()` — maps pipeline Verdicts to ClaimRecords with cite sets
   - `utils/claim_record.py` has `VaultVerdict` enum (vault_supported, not_supported, etc.) and `RouteVerdict` model for results
   - Vault frontmatter `type` values differ from file prefixes: SOURCE notes use subtype values (academic-paper, dataset, etc.), QUOTE notes use "quotation". `DEFAULT_EVIDENCE_TYPES` in vault_serializer.py has the correct set.
   - The vault is at `../ukraine-vote-analysis/vault-main/` (sibling repo, read-only)

3. **Use `workspace/inbox/ukraine-intro-test.txt` for dev testing** (user directive). Full-paper runs reserved for TG 02.7 milestone. However, the test file has NO wikilink citations — for TG 02.4 testing, use fixture notes or construct test inputs with wikilinks.

4. **Cost optimization is deferred** — proceed with Phase 02 implementation.

**Phase plan:** `project-management/phase-plans/phase-02-vault-verification-core.md` (status: IN PROGRESS)

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

### Key decisions made

1–18: See Session 5 handover (preserved in git history).
19. **Vault is trusted for Phase 02 dev** (user directive) even though known errors exist.
20. **ClaimRecord wraps Verdict, doesn't replace it** (Session 6). Verdict already duplicates ValidatedClaim fields; ClaimRecord composes a web_verdict (Optional[Verdict]) plus Phase 02 attributes. Vault verdicts use a separate `VaultVerdict` enum from the web-route `VerificationResult`.
21. **Vault `type` field values differ from file prefixes** (Session 6). SOURCE notes use subtype values (academic-paper, dataset, policy-paper, web-page, source-dataset, data-source). QUOTE notes use "quotation". `DEFAULT_EVIDENCE_TYPES` in vault_serializer.py encodes the correct set, discovered from the real vault.
22. **Citation scope is sentence-level only** (Session 6). Conservative heuristic: a citation applies only to the sentence it appears in, never propagated backward to earlier sentences in the paragraph. A wrong "citation-free" beats a wrong binding.
23. **Sentence splitting replicates the pipeline's exact logic** (Session 6). `ingest/draft_parser.py:split_sentences()` mirrors `claim_extractor/nodes/sentence_splitter.py` lines 59-83 verbatim so `original_index` values match between pre-processing and pipeline output.

### Cost analysis (Session 4)

First full academic paper run: ukraine working paper (7,000 words, 20 sections, 448 claims).

| Model | Tier | Requests | Input tokens | Cost |
|---|---|---|---|---|
| gpt-4o-mini | low | 1,869 | 2.86M | ~$0.47 |
| gpt-4.1 | high | 448 | 3.81M | ~$7.70 |
| gpt-4.1-mini | mid | 4,892 | 3.61M | ~$1.90 |
| **Total** | | **7,209** | **10.27M** | **~$10.07** |

### Test suite

195 tests total (192 pass with `-m "not slow"`, 3 slow tests deselected).

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
| test_ingest.py (slow) | 1 | Docling PDF extraction (~16s) |

### Phase 02 new files (Session 6)

| File | Purpose |
|------|---------|
| `utils/claim_record.py` | ClaimRecord, CitationStatus, VaultVerdict, SuggestedAction, DraftPosition, RouteVerdict |
| `utils/run_config.py` | ResourceManifest, RunProfile |
| `docs/playbook/claim-record-design.md` | Attribute taxonomy — which phase populates each field |
| `ingest/draft_types.py` | Shared types: WikilinkCitation, ParsedSentence, ParsedDraft |
| `ingest/draft_parser.py` | Wikilink parsing, author-year detection, sentence splitting, parse_draft() |
| `ingest/citation_binder.py` | bind_citations(verdicts, parsed_draft) → List[ClaimRecord] |
| `ingest/vault_serializer.py` | VaultNote, SerializedVault, parse_vault_note(), load_vault(), serialize_vault() |
| `tests/fixtures/vault/` | 6 fixture vault notes for offline testing |

### Session 5 vault corrections (sibling repo)

Corrected the ukraine-vote-analysis vault (9 files): ES-11/7 vote tally 98->93 across 9 notes (3 de Carvalho notes with [sic] annotations preserving what the source wrote; 6 downstream notes with corrected figure); "12th ESS"->"11th ESS" in COM-us-shift-qualitative-analysis.md (3 occurrences + rerun warning added). The v2 draft's "98" is left uncorrected as the Phase 02 test-corpus error.

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
