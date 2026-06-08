# Entropy Telemetry: Current Approach & Roadmap

## What it measures

After each generated turn, EXHUMED computes an **entropy** score (0–1) comparing the current speaker's response with the previous speaker's response. High entropy = the two responses diverge. Low entropy = the responses are echoing each other.

This feeds the **DEBATE DIVERSITY** section in the telemetry sidebar — displayed as a percentage and a label (e.g. "High Spread", "Moderate", "Low Spread").

The score is calculated in `backend/utils/text_metrics.py` using `calculate_jaccard_entropy`.

---

## Current implementation: Jaccard on unigrams

```python
def clean_text_for_similarity(text: str) -> set[str]:
    # Normalizes to lowercase, strips punctuation, returns a word set
    ...

def calculate_jaccard_entropy(text1: str, text2: str) -> float:
    intersection = len(words_text1 & words_text2)
    union = len(words_text1 | words_text2)
    jaccard_similarity = intersection / union
    return round(1.0 - jaccard_similarity, 4)
```

**Why it was chosen:** Zero dependencies, O(n), instant. Good enough for a v1 sidebar indicator.

---

## Known pitfalls

### 1. Synonym blindness
Two responses talking about the same idea with different words score as maximally divergent.

> Socrates: *"Virtue requires examination of one's principles."*
> Napoleon: *"Excellence demands rigorous scrutiny of one's standards."*

Jaccard similarity ≈ 0 (no shared content words) → entropy ≈ 1.0 → reports "full divergence".
In reality these responses are semantically identical — both argue that self-scrutiny leads to excellence.

### 2. Shared function words inflate overlap
Short responses with high stop-word density (articles, prepositions, conjunctions) share many tokens even when the ideas are completely different. Filtering stop-words helps but doesn't solve the underlying problem.

### 3. Phrase blindness
"Decisive action" as a phrase concept is invisible. Jaccard treats "decisive" and "action" as independent tokens, so *"decisive action wins wars"* and *"bold, swift action decides campaigns"* score as low-overlap even though they express the same claim.

### 4. Response length asymmetry
A one-sentence response vs. a five-sentence response will artificially inflate the union and suppress Jaccard similarity, biasing entropy upward regardless of actual content overlap.

---

## Better solutions (in order of implementation cost)

### Option A — Bigram-enhanced Jaccard ❌ tested and rejected

**Hypothesis:** adding two-word phrases to the token set would let shared phrases like "social contract" or "free will" register as overlap even when surrounding words differ.

**Result:** tested against six realistic debate pairs. Bigrams made entropy *higher* in every case, including the echoing case (two near-identical responses scored 0.41 with unigrams → 0.64 with bigrams — wrongly reported as more divergent).

**Why it backfires — the math:**

A text with N words produces N unigrams. Adding bigrams gives (N-1) extra tokens, nearly doubling the vocabulary set size to ~(2N-1). The same happens for text B. So the **union** grows by roughly 2×. But shared bigrams require *adjacent word pairs* to match exactly in both texts — far stricter than unigram overlap. The intersection grows by much less than 2×. Since Jaccard = intersection / union, a smaller ratio means higher entropy across the board.

The only scenario where bigrams would help is when both texts are near-verbatim copies of each other — which is exactly when plain Jaccard already scores low entropy correctly. For all other cases (different phrasing, shared concepts, partial overlap), bigrams inflate divergence and make the metric less accurate, not more.

### Option B — TF-IDF cosine similarity (moderate change, numpy only)
Weight words by their importance instead of treating all words equally. Build sparse TF-IDF vectors and compute cosine similarity.

**Gain:** Discounts stop-words automatically. More robust to length asymmetry.
**Cost:** Requires numpy (already available on the backend). ~30 lines of code. Still lexical.

### Option C — Semantic cosine similarity (significant change, requires embedding)
Embed both responses using the existing `SentenceTransformerEmbeddingProvider` (BGE) and compute cosine similarity between the two vectors.

```python
vec1 = embedding_provider.embed(text1)
vec2 = embedding_provider.embed(text2)
entropy = 1.0 - cosine_similarity(vec1, vec2)
```

**Gain:** True semantic comparison. Synonyms, paraphrases, and conceptual overlaps are correctly detected.
**Cost:** Two additional embedding calls per turn (~50–150ms each if using the local fallback model). The primary Upstash path sends `data=text` so a vector query costs only a REST call, but embedding-only calls need either the local model or a separate Upstash query.
**Mitigation:** Cache embeddings keyed by `hash(text)` — within a session the same response text never appears twice so cache hit rate is low, but the call is cheap if using Upstash's native endpoint.

### Option D — Use retrieval score as a grounding proxy (free, already available)
The top RAG match score is already available at turn finalization time. A high top-score (e.g. 0.90+) means the response is tightly grounded in the speaker's knowledge base. A low score means the LLM drifted from its sources.

This doesn't measure inter-speaker divergence but measures **grounding quality**, which is arguably more actionable for EXHUMED's use case.

---

## Recommendation

Keep Jaccard for now — it's cheap and "close enough" for a sidebar diversity indicator. Option A (bigrams) was tested and rejected. The real upgrade path is **Option C** (semantic cosine via BGE) once the system is stable and the per-turn embedding call latency is acceptable, or **Option D** (retrieval score as grounding proxy) as a free intermediate step that repurposes data already available at turn finalization time.
