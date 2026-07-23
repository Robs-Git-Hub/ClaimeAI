# Session Handover

**Last Updated:** 2026-07-23 (Session 5, outgoing)
**Current Status:** Phase 01 COMPLETE. Phase 02 APPROVED — ready for implementation.

---

## Start Here

**Outgoing session completed:** Phase 01 closed (01.5.3 `/claimify` skill end-to-end test passed via OpenRouter); Phase 02 plan approved by user; standard dev test file established (`workspace/inbox/ukraine-intro-test.txt`); vault corrections in sibling repo (98->93 vote tally across 9 notes, "12th ESS" -> "11th ESS" in commission brief).

**Incoming session should:**

1. **Begin Phase 02 implementation with TG 02.1** — Claim Record, Run Profiles, Resource Manifest. This is the data-model foundation: Pydantic models for the multi-attribute claim record, `light`/`heavy` run profiles, and a per-run resource manifest. See `project-management/phase-plans/phase-02-vault-verification-core.md` for full spec and design pillars.

2. **Use `workspace/inbox/ukraine-intro-test.txt` for dev testing** (user directive). It costs cents per run. Baseline: 15 claims, 10 supported / 5 refuted. The five refuted include pipeline mistakes to fix (decomposition artifact, wrong verdict category) and one genuine paper error the pipeline correctly caught (98 vs 93 votes). Reserve full-paper runs for the TG 02.7 milestone. See memory `phase02-standard-test-file` for detailed characterization.

3. **Cost optimization is deferred** — the user chose to proceed with Phase 02 rather than tune config.toml settings first. The $10/paper cost for full runs is managed by using the cheap test file during development.

**Phase plan:** `project-management/phase-plans/phase-02-vault-verification-core.md` (status: APPROVED)

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

1--12: See Session 4 handover (preserved in git history).
13. **Eight design pillars agreed for Phase 02** — see phase plan. Do not re-litigate.
14. **Cost optimization is a first-class concern** but deferred in favor of Phase 02 implementation.
15. **Phase 01 complete, Phase 02 approved** (Session 5). User signed off on the TG 02.1--02.7 breakdown.
16. **Standard dev test file established** (Session 5): `workspace/inbox/ukraine-intro-test.txt` for all Phase 02 development testing. Full-paper runs reserved for TG 02.7 milestone only.
17. **OpenAI account out of credit** (Session 5). Use `LLM_PROVIDER=openrouter` env override or top up the account before OpenAI-provider runs.
18. **De Carvalho (2025) SAIIA article contains a factual error** — states "98 votes" for ES-11/7 (actual: 93). All vault notes corrected with [sic] annotations. The v2 draft's "98" is deliberately left uncorrected as a test-corpus error for Phase 02 vault verification.
19. **Vault is trusted for Phase 02 dev** (user directive) even though known errors exist — vault verification of relied-upon notes is a future phase.

### Cost analysis (Session 4)

First full academic paper run: ukraine working paper (7,000 words, 20 sections, 448 claims).

| Model | Tier | Requests | Input tokens | Cost |
|---|---|---|---|---|
| gpt-4o-mini | low | 1,869 | 2.86M | ~$0.47 |
| gpt-4.1 | high | 448 | 3.81M | ~$7.70 |
| gpt-4.1-mini | mid | 4,892 | 3.61M | ~$1.90 |
| **Total** | | **7,209** | **10.27M** | **~$10.07** |

### Test suite

87 offline tests (`poetry run pytest -q -m "not slow"`). 1 slow test (docling extraction, ~16s with cached models).

| File | Count | Covers |
|------|-------|--------|
| test_models.py | 24 | MODEL_REGISTRY, tier resolution, provider routing, reasoning effort |
| test_settings.py | 13 | Pydantic settings, env var validation |
| test_ingest.py | 31 | PDF extraction, chunking, text dispatch, report rendering |
| test_cost_tracking.py | 12 | Search cost counter, estimates, free-tier balance, print_summary |
| test_config.py | 7 | TOML loading, sections, fallbacks, real config.toml validation |

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
| 2026-07-23 | Session 5: Phase 01 closed (01.5.3 /claimify skill e2e test passed via OpenRouter after OpenAI 429). Phase 02 approved. Standard dev test file established. Vault corrections: 98->93 across 9 notes with [sic] on de Carvalho source notes; 12th->11th ESS in commission brief with rerun warning. Completion audit caught 5 doc-sync issues (Phase 01 plan status, stale Phase 02 deps, CLAUDE.md layout/key-files, HANDOVER file count). check-full-completion skill bumped to v1.2.0 (Sonnet routing). 4 commits (ClaimeAI) + 1 commit (ukraine-vote-analysis) + 1 commit (claude-multi-repo-instructions-and-lessons). |
