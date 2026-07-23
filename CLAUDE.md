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
| `security/`        | API key auth for LangGraph                           |
| `scripts/`         | CLI dev tools and runners                            |
| `docs/`            | Project documentation                                |
| `project-management/` | Phase plans and task tracker                      |

### Key Files

- `langgraph.json` — graph registry for LangGraph CLI
- `pyproject.toml` — Python dependencies (Poetry)
- `utils/settings.py` — env var validation (Pydantic), incl. `LLM_PROVIDER` / `OPENROUTER_API_KEY`
- `utils/models.py` — `get_llm()` factory + `MODEL_REGISTRY` (per-role model per provider)
- `claim_extractor/llm/config.py` — extraction temperature constants (models live in the registry)
- `claim_verifier/llm/config.py` — verification temperature constants (models live in the registry)
- `docs/llm-providers.md` — role × provider model mapping table
- `docs/websearch-and-costs.md` — Exa/Tavily and LLM cost estimates

## Pipeline

```
Text → Sentence Split (NLTK) → Selection (voting) → Disambiguation (voting)
     → Decomposition → Validation → [claims]
     → Generate Search Query → Web Search (Exa/Tavily) → Evaluate Evidence
     → Verdict: Supported | Refuted | Insufficient | Conflicting
```

### Quality gates

- Selection and disambiguation use 3 LLM completions with 2/3 majority voting. Do not reduce this — it is the primary quality mechanism.
- Evidence evaluation uses the most capable model tier (GPT-4.1 on OpenAI, Claude Opus on OpenRouter — see `MODEL_REGISTRY` in `utils/models.py`). Never map this role below Opus/GPT-4.1 tier.
- Up to 5 search iterations per claim if evidence is insufficient.

## Running

```bash
# Install
poetry install

# Start LangGraph dev server (--allow-blocking needed for NLTK's sync tokenizer)
poetry run dev
# Or manually: langgraph dev --no-browser --allow-blocking

# Run fact-checker on text
python scripts/run_fact_checker.py
```

### Required env vars

```
OPENAI_API_KEY=sk-proj-...
EXA_API_KEY=...
REDIS_URI=redis://localhost:6379
```

Optional: `TAVILY_API_KEY`, `LANGSMITH_API_KEY`, `LLM_PROVIDER` (`openai` default | `openrouter`), `OPENROUTER_API_KEY` (`sk-or-...`, required when `LLM_PROVIDER=openrouter`)

## Conventions

- All LLM calls go through `utils/models.py:get_llm()` — nodes pass a `role` (`extraction`, `query_generation`, `search_decision`, `evidence_evaluation`) and the registry resolves the model for the active provider (OpenAI via `init_chat_model`, OpenRouter via `ChatOpenAI` against `https://openrouter.ai/api/v1`)
- Structured output via `llm.with_structured_output(PydanticModel)` everywhere
- Voting via `utils/llm.py:process_with_voting()` — N completions, M required successes
- Search provider configured in `claim_verifier/config/nodes.py` (default: `exa`)
