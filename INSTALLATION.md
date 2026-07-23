# Installation

## Prerequisites

- **Python 3.11+** — from [python.org/downloads](https://www.python.org/downloads/) or your package manager
- **Poetry 2.1+** — dependency management ([install guide](https://python-poetry.org/docs/#installation))
- **LangGraph CLI** — `pip install "langgraph-cli[inmem]"`
- **Docker** (optional) — for running Redis and Postgres locally via `docker compose up -d`

Verify everything is ready:

```bash
python --version     # Should be 3.11+
poetry --version     # Should be 2.1+
langgraph --version
```

## Setting Up the Project

```bash
# Clone and change into the project directory
git clone https://github.com/Robs-Git-Hub/ClaimeAI.git
cd ClaimeAI

# Install Python dependencies
poetry install

# Create your env file and fill in your keys
cp .env.example .env

# (Optional) Start Redis and Postgres in Docker
docker compose up -d

# Start the LangGraph dev server
poetry run dev
```

## Environment Variables

Edit `.env` with the following:

| Variable | Required | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | Yes | Must be a project key with the `sk-proj-` prefix |
| `LLM_PROVIDER` | Optional | `openai` (default) or `openrouter` — selects the LLM provider (see `docs/llm-providers.md`) |
| `OPENROUTER_API_KEY` | Optional | Required when `LLM_PROVIDER=openrouter`; must start with `sk-or-` |
| `EXA_API_KEY` | Yes | Exa web search ([exa.ai](https://exa.ai/)) — the default search provider |
| `TAVILY_API_KEY` | Optional | Alternative search provider ([tavily.com](https://tavily.com/)) |
| `LANGSMITH_API_KEY` | Optional | LangSmith tracing |
| `DATABASE_URI` | Optional | Postgres checkpointing (e.g. `postgres://postgres:postgres@localhost:5432/main`) |
| `REDIS_URI` | Yes | e.g. `redis://localhost:6379` |
| `REDIS_URL` | Yes | Set to the same value as `REDIS_URI` — see gotcha below |

> **Gotcha:** Both `REDIS_URI` and `REDIS_URL` must be set to the same value. LangGraph overrides the `REDIS_URI` variable at runtime, so the application reads `REDIS_URL` to stay compatible.

## Troubleshooting

- **Poetry installation fails**: Try `pip install poetry` or `uv tool install poetry` as an alternative
- **LangGraph CLI errors**: Ensure you have Python 3.11+ and try `pip install --upgrade "langgraph-cli[inmem]"`
- **Package conflicts**: Try `poetry env remove --all` and then `poetry install` again

## Running the Fact-Checker

With the dev server running (`poetry run dev`), three graphs are available: `claim_extractor`, `claim_verifier`, and `fact_checker`.

You can also run the pipeline directly from the CLI:

```bash
poetry run python scripts/run_fact_checker.py
```
