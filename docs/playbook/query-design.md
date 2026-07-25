# Query Design for Evidence Retrieval

**Purpose:** How to turn a factual claim into a search query that retrieves useful evidence without biasing the result.

## The problem

A fact-checking pipeline must search the web for evidence about a claim, then evaluate what it finds. The phrasing of the search query determines what comes back. A poorly phrased query can bias the search engine (and any downstream synthesis layer like PixSerp) toward confirming the claim — even when the claim is wrong.

This is the **verification bias**: if you search for "did X happen", both search engines and LLMs anchor on X and try to confirm it. The pipeline's job is to find evidence that lets the evaluator judge independently — not to pre-judge through query phrasing.

## Three query shapes

Given the claim: *"89 countries voted in favour of Resolution R"*

### 1. Leading verification

```
Did 89 countries vote in favour of Resolution R?
```

**Pros:**
- Highly specific — narrow result set, minimal noise
- Search engines match the exact terms, so if "89" appears in a page, it will be found
- Fastest for the reviewing agent to process (few results, all on-topic)

**Cons:**
- **Plants the number "89" in the query.** Search engines return pages mentioning 89 even if the real number is different — pages saying "93" may rank lower or not appear at all because they don't match the query terms.
- **Synthesis-layer amplification.** PixSerp's Session 15 tests showed this directly: when asked to "verify" claim 3 (98 votes, actual 93), PixSerp searched for "98", found nothing, and reported "not supported" — rather than discovering the real figure. The synthesizer anchored on the planted number.
- **Confirmation bias in iterative search.** Our pipeline runs up to 5 search iterations per claim. If the first query plants a wrong number, the search-decision LLM may keep refining around that number rather than stepping back to ask what the real number is.
- The fact-checking literature identifies this as the most dangerous query shape — it systematically suppresses the counter-evidence that would produce a Refuted verdict.

**When it's appropriate:** Only when the pipeline's goal is to find the exact source that states a specific number (e.g. locating the official UN voting record page). Never as the default for evidence retrieval.

### 2. Open factual question

```
How many countries voted in favour of Resolution R?
```

**Pros:**
- **Doesn't plant the number.** The search engine returns pages about the vote itself — the correct figure surfaces naturally regardless of what the claim states.
- **Counter-evidence appears organically.** If the real answer is 93, pages stating 93 rank just as well as pages stating any other number.
- **The reviewing agent sees the truth.** The evidence evaluator receives source material containing the actual figure and can compare it against the claim independently.

**Cons:**
- Broader result set — some results may discuss Resolution R in general terms without stating the vote count.
- Requires the evidence summarization step (mid tier) to extract the claim-relevant content from noisier results.
- May retrieve fewer results if the search engine doesn't find the question phrasing in page content (search engines are optimised for keywords, not questions — though this gap has narrowed significantly with AI-era search APIs like PixSerp and Exa).

**When it's appropriate:** Default for fact-checking. The broader results are handled by the existing mid-tier summarization step, which is cheap and already prompted to preserve refuting content. The cost of broader results is one cheap LLM call; the cost of leading results is a wrong verdict.

### 3. Keyword neutral

```
Resolution R vote count results
```

**Pros:**
- Most search-engine-friendly — matches how traditional SERP APIs (Serper, Google) index pages.
- Highest recall — casts the widest net, finds pages that discuss the vote from any angle.
- No embedded assumption about what the answer should be.
- Works well with SERP-only providers (Serper, SearXNG) that return snippets ranked by keyword relevance.

**Cons:**
- Lowest precision — results may include procedural pages, news commentary, or pages about other resolutions with similar names.
- Puts the most burden on the reviewing agent to separate signal from noise.
- Less effective with AI-native search APIs (PixSerp, Exa) that perform better with natural-language queries.
- May require more search iterations to converge on relevant evidence.

**When it's appropriate:** When using traditional SERP APIs (Serper at $1/1k) as the search step, especially in a two-stage design where a fetch/extract stage (crawl4ai) follows to get full page content. The keyword query finds the right pages; the fetch stage gets the evidence; the evaluator judges it.

## Interaction with the pipeline

Our pipeline has a built-in defence against noisy results: the **mid-tier evidence summarization step** (`claim_verifier/evidence_summarization.py`). Raw search results pass through this step before the high-tier evaluator sees them. The summarizer is prompted to:
- Extract content relevant to the specific claim
- Preserve refuting content (not just confirmations)
- Maintain URL attribution from the original sources

This means **open factual questions are safe** — the summarizer handles the noise at mid-tier cost ($0.40–1.60/M tokens), which is far cheaper than the wrong verdict that leading queries risk.

The existing query generation prompt (`claim_verifier/prompts.py`, `QUERY_GENERATION_INITIAL_SYSTEM_PROMPT`) currently instructs: *"Include key entities, names, dates, and specific details from the claim"* and *"Keep it concise (5-15 words optimal)"*. This biases toward the keyword-neutral or leading shapes. If the pipeline is updated to use open factual questions as the default, this prompt should be revised — but note that the prompt also says *"Design to find both supporting AND contradictory evidence"*, which is the right intent even if the keyword-style output can't fully deliver on it.

## Choosing a strategy

If unconstrained by speed or cost, running all three shapes per claim and combining the results before evaluation would maximise evidence coverage — leading finds exact-match pages, open factual finds the correct answer, keyword neutral finds the broadest context. The evaluator would see the union of all evidence.

In practice, the pipeline will use one or two shapes per claim. The recommendation, ordered by priority:

1. **Open factual question as the default.** Avoids verification bias; the summarizer handles noise. This should be the first search iteration.
2. **Keyword neutral as the fallback.** If the open factual question returns insufficient evidence (the pipeline's iterative search loop), the retry query can drop to keyword form to cast a wider net. This is already roughly what `QUERY_GENERATION_ITERATIVE_SYSTEM_PROMPT` does — it instructs the LLM to *"Try alternative phrasing or different scope"* on retry.
3. **Leading verification only for targeted confirmation.** If the evaluator has already identified a specific factual claim from the open search (e.g. "the vote count was 93") and needs to verify that specific number against an authoritative source, a leading query like `"Resolution R 93 votes official record"` is appropriate — but only as a directed follow-up, never as the first search.

## Provider-specific implications

**PixSerp:** The synthesized answer amplifies leading-query bias into hallucination (Session 15: deep tier confidently confirmed "fifteen resolutions" from an irrelevant source). Use open factual questions and discard the synthesized answer; use citation `snippet` fields as evidence instead.

**Exa:** Neural/semantic search handles natural-language questions well. Open factual questions are a good fit. Exa's 2 KB content cap means the evidence is already focused.

**Tavily:** Returns full page content (up to 486 KB). Open factual questions work, but the mid-tier summarization step is essential to extract the relevant passage from the full-page dump.

**Serper / SERP APIs:** Keyword neutral is the native format. These APIs index by keywords, not by question semantics. In a two-stage design (SERP → fetch), the keyword query finds the URLs; the fetch/extract stage gets the evidence.

## Relationship to D10 (support confirmation)

The D10 cross-check (vault/corpus-supported claims get one web confirmation) is a structural defence against the same problem this doc addresses at the query level. Even if a leading query produces a false confirmation, D10 sends the claim through an independent web check. The two defences are complementary: query design reduces false confirmations at the input; D10 catches any that slip through at the routing level.
