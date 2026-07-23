# Web Search Providers and Costs

## Exa AI and Tavily

ClaimeAI uses **Exa AI or Tavily to search the web for evidence** relevant to each extracted factual claim. The selected service returns source links and webpage text, which an LLM then evaluates to determine whether the claim is supported, refuted, conflicting or insufficiently evidenced. ClaimeAI uses one provider at a time and currently defaults to Exa.

**Exa AI** is a search engine designed specifically for AI systems. Its semantic search can match the meaning of detailed queries rather than relying solely on exact keywords. ClaimeAI uses Exa's neural-search mode and retrieves up to three webpage excerpts for each query.

**Tavily** is a broader web-retrieval service for AI agents. In addition to search, it provides extraction, crawling, site mapping and research tools. Its search API combines web search with filtering, ranking and extraction of content suitable for use by an LLM. In ClaimeAI, Tavily returns up to three results with raw webpage content.

The main practical difference is that **Exa emphasizes semantic search and targeted retrieval**, while **Tavily provides a wider collection of search and web-extraction capabilities**. Either can perform ClaimeAI's evidence-retrieval task, and their output quality should ideally be compared using a representative test set.

### Estimated search costs

ClaimeAI can make between one and five searches for each claim, depending on whether it finds adequate evidence or needs to retry. The estimates below assume pay-as-you-go pricing and exclude the separate cost of the LLM calls used for claim extraction, query generation and evidence evaluation.

| Provider               | Cost per claim | Cost for 50 claims |
| ---------------------- | -------------: | -----------------: |
| Exa standard search    |  $0.007–$0.035 |    **$0.35–$1.75** |
| Tavily basic search    |  $0.008–$0.040 |    **$0.40–$2.00** |
| Tavily advanced search |  $0.016–$0.080 |    **$0.80–$4.00** |

Exa currently charges **$7 per 1,000 standard searches** and provides $20 of initial credit followed by $10 of free monthly credit. Tavily charges **$0.008 per credit** on pay-as-you-go pricing; basic searches consume one credit and advanced searches consume two. Tavily also provides 1,000 free credits per month.

These are upper and lower estimates rather than fixed document costs. A claim resolved by the first search costs substantially less than one that uses all five permitted iterations.

## LLM costs

LLM usage is driven by the three-tier model mapping in `MODEL_REGISTRY` (`utils/models.py`). See `docs/playbook/model-tier-selection.md` for full rationale. Approximate list prices per million tokens (input / output):

| Tier | OpenAI model | ~$/M in/out | OpenRouter model | ~$/M in/out |
| --- | --- | --- | --- | --- |
| low (extraction) | `gpt-4o-mini` | $0.15 / $0.60 | `google/gemma-4-26b-a4b-it` | $0.06 / $0.33 |
| mid (query gen, search decision) | `gpt-4.1-mini` | $0.40 / $1.60 | `anthropic/claude-haiku-4.5` | $1 / $5 |
| high (evidence evaluation) | `gpt-4.1` | $2 / $8 | `anthropic/claude-sonnet-5` | $2 / $10 |

Rough order of magnitude per document: extraction makes 3 voting completions per sentence for two stages plus decomposition/validation on small prompts (typically cents), while evidence evaluation runs once per claim over up to ~15 retrieved snippets — this is the dominant LLM cost.

> Prices checked against openrouter.ai on 2026-07-22. OpenAI prices are approximate and **need confirmation against openai.com/pricing** before budgeting. OpenRouter pricing shown is standard; BYOK pricing may differ.
