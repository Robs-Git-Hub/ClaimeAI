# LLM Providers and Model Mapping

ClaimeAI supports two LLM providers, selected via `pipeline.llm_provider` in
`config.toml` (`openai` by default, or `openrouter`). Each pipeline node maps to one
of three cost/quality tiers per provider — the `[models.*]` sections in `config.toml`
are the single source of truth. Nodes only ever request a tier
(`get_llm(tier="low")`, etc.), so changing `llm_provider` in `config.toml` is the only
thing anyone needs to touch to move the whole pipeline between providers.

For the full rationale behind each model choice, see
[docs/playbook/model-tier-selection.md](playbook/model-tier-selection.md).

## Configuration

| Setting | Location | Values | Notes |
| --- | --- | --- | --- |
| `llm_provider` | `config.toml` `[pipeline]` | `openai` (default), `openrouter` | Also overridable via `LLM_PROVIDER` env var |
| `OPENAI_API_KEY` | `.env` | `sk-proj-...` | Required when provider is `openai` |
| `OPENROUTER_API_KEY` | `.env` | `sk-or-...` | Required when provider is `openrouter` |

OpenRouter is accessed through its OpenAI-compatible endpoint
(`https://openrouter.ai/api/v1`) via `langchain_openai.ChatOpenAI`, so structured
output and temperature behave identically across providers.

## Tier × provider model mapping

| Tier | Used by | `openai` | `openrouter` | Price (in/out per 1M) |
| --- | --- | --- | --- | --- |
| `low` | selection, disambiguation, decomposition, validation | `gpt-4o-mini` | `google/gemma-4-26b-a4b-it` | $0.15/$0.60 · $0.06/$0.33 |
| `mid` | generate_search_query, search_decision | `gpt-4.1-mini` | `anthropic/claude-haiku-4.5` | $0.40/$1.60 · $1/$5 |
| `high` | evaluate_evidence | `gpt-4.1` | `anthropic/claude-sonnet-5` | $2/$8 · $2/$10 |

Notes:

- **The `high` tier must never be downgraded.** `gpt-4.1` is OpenAI's smartest
  non-reasoning model; `claude-sonnet-5` is Anthropic's frontier hybrid-reasoning
  model. Evidence evaluation produces the final verdict and is the quality gate.
- **Reasoning effort:** The OpenRouter `high` tier (Sonnet 5) uses
  `reasoning_effort="medium"` via `REASONING_CONFIG` in `utils/models.py`. This
  is set automatically when `get_llm(tier="high")` is called with the OpenRouter
  provider — nodes don't need to know about it.
- OpenRouter model IDs verified against [openrouter.ai](https://openrouter.ai)
  on 2026-07-23. Re-confirm if models are updated.
- The 3-completion / 2-of-3 voting quality gate (selection and disambiguation)
  applies on both providers; multi-completion calls run at temperature 0.2.
- OpenRouter pricing shown is standard; BYOK pricing may differ.
