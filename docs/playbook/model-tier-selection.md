# Model Tier Selection Playbook

How we chose which LLM models to assign to each cost/quality tier, and why.

Last updated: 2026-07-22 (Session 2)

## Design principle

The pipeline uses three tiers (`low`, `mid`, `high`). Nodes request a tier, never a concrete model name. Swapping `LLM_PROVIDER` in `.env` moves the whole pipeline between providers — one config change, no code changes.

Tiers are matched **across providers by class and cost band**, not by name. A "low" model on OpenAI should be roughly the same class of model as "low" on OpenRouter — similar capability, similar cost order-of-magnitude, similar speed characteristics.

## The tiers

### Low — high-volume structured extraction

**Pipeline nodes:** sentence selection (×3 completions), disambiguation (×3), decomposition (×3), validation (×1).

**Why this tier exists:** These nodes run 3 completions per item for majority voting and process every sentence in the input. Volume is high, tasks are mechanical (binary keep/discard, pronoun resolution, sentence splitting, verifiability check). The model needs to follow structured output schemas reliably, but doesn't need deep reasoning.

**What to look for:** cheapest model that reliably produces structured output, fast, good instruction-following.

| Provider | Model | Price (in/out per 1M) | Key characteristics |
|----------|-------|----------------------|---------------------|
| OpenAI | `gpt-4o-mini` | $0.15 / $0.60 | Cheapest OpenAI mini. 128K context. Fast, efficient. Being superseded by gpt-4.1-nano but still widely deployed. |
| OpenRouter | `google/gemma-4-26b-a4b-it` | $0.06 / $0.33 | Google DeepMind MoE model. 25.2B total params but only 3.8B activate per token — near-31B quality at a fraction of the compute. 262K context. Apache 2.0 licensed. Multimodal capable. Native function calling and structured output. BYOK pricing. |

### Mid — search query crafting and search decisions

**Pipeline nodes:** search query generation (×1 per iteration), search decision (×1 per iteration, up to 5 iterations per claim).

**Why this tier exists:** These nodes need to reason about what evidence would verify or refute a claim, craft effective search queries, and judge whether retrieved evidence is sufficient or another search round is needed. More reasoning than extraction, but not the final verdict.

**What to look for:** good instruction-following and reasoning at moderate cost. Not a frontier model — the tasks are well-scoped.

| Provider | Model | Price (in/out per 1M) | Key characteristics |
|----------|-------|----------------------|---------------------|
| OpenAI | `gpt-4.1-mini` | $0.40 / $1.60 | OpenAI's best small model. 1M context. Matches GPT-4o intelligence at 83% lower cost with half the latency. Strong instruction-following. Recommended mini for most tasks. |
| OpenRouter | `anthropic/claude-haiku-4.5` | $1 / $5 | Anthropic's fastest model. 200K context. Matches Sonnet 4 on coding benchmarks (73% SWE-bench). Near-frontier intelligence at lowest Anthropic price. The closest Anthropic model to mini-class — the next step up (Sonnet 5 at $2/$10) is a frontier model, not a mini. |

### High — evidence evaluation (quality gate)

**Pipeline nodes:** evidence evaluation (×1 per claim).

**Why this tier exists:** This is the final verdict — Supported, Refuted, Insufficient Information, or Conflicting Evidence. The model must carefully weigh retrieved web evidence against the claim, handle nuance (partial support, conflicting sources, paywalled content), and produce a reasoned judgment. This is the primary quality mechanism of the verifier.

**What to look for:** smartest model available that balances intelligence, speed, and cost. Never downgrade this tier — verdict quality is the product.

| Provider | Model | Price (in/out per 1M) | Key characteristics |
|----------|-------|----------------------|---------------------|
| OpenAI | `gpt-4.1` | $2 / $8 | **OpenAI's smartest non-reasoning model.** 1M context. Replaced GPT-4o as the recommended API model. Best instruction-following and coding in OpenAI's lineup (non-o-series). Chosen for evidence evaluation because it balances intelligence, speed, and cost. |
| OpenRouter | `anthropic/claude-sonnet-5` | $2 / $10 | **Anthropic's most capable Sonnet — a hybrid-reasoning model.** 1M context. Frontier performance across coding, agents, and professional work. Supports adaptive reasoning with selectable effort levels (low/medium/high/max/x-high) — the reasoning level should be set when constructing the client for evidence evaluation. Price-comparable to gpt-4.1 ($2/$8 vs $2/$10). Anthropic's recommended model for production use. |

## Why not Opus?

The original mapping used `claude-opus-4.8` ($5/$25) at high tier. This was over-specced:

- Opus is 2.5× the cost of gpt-4.1 ($5/$25 vs $2/$8) for a tier that's meant to be comparable across providers.
- Sonnet 5 is described as "frontier performance" and is price-matched to gpt-4.1.
- Opus would only be warranted if we added an "ultra" tier for tasks requiring Anthropic's absolute best — and even then, the cost difference should be a conscious choice.

## Why Gemma 4 26B for low tier?

The original mapping used `claude-haiku-4.5` ($1/$5) at low tier. This works but is ~7× more expensive than Gemma 4 on input and ~15× on output. For the extraction nodes that run 3 completions per sentence with structured output:

- Gemma 4's MoE architecture (3.8B active parameters) is fast and efficient.
- It has native function calling and structured output support — exactly what the extraction nodes need.
- At $0.06/$0.33 it's the cheapest option that still delivers reliable structured output.
- The user runs BYOK pricing on OpenRouter, making this even more cost-effective.
- 262K context is more than sufficient (extraction processes individual sentences with ~5 sentences of context).

Haiku 4.5 moves to mid tier where its "near-frontier intelligence" is better utilized for the reasoning-adjacent search query and search decision tasks.

## Cost comparison per claim (estimates)

Assumes 1 claim, 3 search iterations (average), structured output overhead ~1.5× raw tokens.

| Component | OpenAI cost | OpenRouter cost (proposed) |
|-----------|------------|---------------------------|
| Extraction (low × ~10 completions) | ~$0.003 | ~$0.001 |
| Query gen + search decision (mid × ~6 calls) | ~$0.004 | ~$0.010 |
| Evidence evaluation (high × 1 call) | ~$0.010 | ~$0.012 |
| **Subtotal LLM per claim** | **~$0.017** | **~$0.023** |
| Exa search (1–5 queries) | $0.007–$0.035 | $0.007–$0.035 |

These are rough estimates — actual costs depend on input length, evidence volume, and retry iterations.

## Adding a new provider

To add a third provider (e.g., a local Ollama instance):

1. Add the provider key to `MODEL_REGISTRY` in `utils/models.py` with models for all three tiers.
2. Add provider-specific client construction in `utils/models.py` (following the `_get_openrouter_llm` pattern).
3. Add the provider value to the `llm_provider` validator in `utils/settings.py`.
4. Add any required API key field to settings.
5. Update this playbook with the model choices and rationale.
