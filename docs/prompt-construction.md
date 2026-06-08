# Prompt Construction

This document describes exactly how the backend assembles the user prompt for each debate turn.

The system prompt (persona, voice, model config) lives on the agent record and is sent separately as the `system` role message. This document covers the `user` role message only.

---

## The Four Calls

Before a prompt can be built, the backend makes four storage calls per turn.

Calls 1, 2, and 3 can all run concurrently — the vector query no longer depends on the context messages because the query text is the topic alone. In the current implementation calls 1 and 2 are gathered first, then call 3 runs; this is a known optimization opportunity.

| # | Store | Call | Returns |
|---|---|---|---|
| 1 | Redis | `fetch_agent_config(agent_id)` | Speaker persona, system prompt, model config |
| 2 | Redis | `fetch_context_messages(session_id, limit=4, topic, anchor_agent_id)` | Last 4 turns for the active topic + current speaker's last turn if not in window |
| 3 | Vector | `vector_index.query(data=topic, filter=agent_id, top_k=11)` | Up to 11 semantically matched chunks |
| 4 | Vector | `vector_index.fetch(ids=[neighbor_ids])` | Adjacent chunks for context enrichment |

Call 4 depends on call 3 (neighbor IDs come from the query results). Calls 3 and 4 are therefore sequential.

---

## Building the Vector Query

```python
# turn_workflow.py — prepare_turn_inputs()
query_text = topic
```

The query is the discussion topic only. An earlier implementation appended the last 200 characters of the previous speaker's response to bias retrieval toward the live debate state, but this was removed because:

1. The previous response is already in the prompt via the context block — the LLM sees it in full.
2. Another speaker's vocabulary steers the embedding away from the current speaker's own knowledge base.
3. A single vector cannot represent both signals cleanly; one dilutes the other.

Context-awareness is now handled entirely by the 4-turn history window in the prompt, not by the retrieval query.

---

## Chunk Selection

Selection happens in four layers inside `database.py — get_agent_context()`.

### Layer 1 — Agent filter

```python
filter_expression = f"agent_id = '{agent_id}'"
```

Applied at the vector index level before any scoring. A speaker can only retrieve chunks from their own corpus. Cross-agent contamination is structurally impossible.

### Layer 2 — Semantic ranking

```python
fetch_k = top_k * 2 + 1  # 11 when top_k=5

results = self.vector_index.query(
    data=query_text,
    top_k=fetch_k,          # fetch a wider pool for diversity filtering
    filter=filter_expression,
    include_data=True,
)
```

Upstash Vector embeds the query text server-side using BGE_BASE_EN_V1_5 (768-dim) and returns the top 11 chunks by cosine similarity from that agent's namespace. A wider pool is fetched so the diversity filter in layer 4 has enough candidates to fill the final 5 slots from distinct sources.

### Layer 3 — Score threshold

```python
_VECTOR_SCORE_THRESHOLD = 0.60

matches = [m for m in matches if (m.get("score") or 0.0) >= 0.60]
```

Any chunk scoring below 0.60 is dropped. If all candidates fall below the threshold the match list is empty and the prompt falls back to the no-retrieval path.

In practice, scores from a focused topic query against a speaker's own corpus cluster between 0.65 and 0.82 — the distribution is narrow because BGE embeddings in high-dimensional space are never truly far apart within a thematically coherent corpus.

### Layer 4 — Source diversity filter

```python
# max 2 chunks from any single source_slug
matches = self._apply_source_diversity(matches, max_per_source=2)
```

Without this filter, all 5 result slots could come from adjacent chunks within the same source document (e.g. five consecutive passages from Napoleon's memoirs). The diversity filter caps any single source at 2 chunks, ensuring retrieval draws from multiple parts of a speaker's corpus. The filter is skipped entirely when all candidates share one source — single-source speakers receive a full top_k result without artificial capping.

### Layer 5 — Adaptive top_k

```python
top_score = matches[0].get("score") or 0.0
effective_top_k = top_k if top_score >= 0.72 else min(top_k + 2, len(matches))
matches = matches[:effective_top_k]
```

When the best-scoring chunk is strong (≥ 0.72), the standard top 5 are returned. When the best score is weak (≥ 0.60 but < 0.72), the cap expands to 7 — pulling more candidates from the already-fetched pool of 11 to compensate for lower individual relevance. No extra Upstash call is made; this is a free operation over the candidates already in memory.

---

## Neighbor Enrichment

Neighbor enrichment is currently **disabled** (`neighbor_window=0`). Each matched chunk is sent to the LLM as-is without fetching adjacent chunks.

**Why disabled:** chunks are ~950 characters (2–3 paragraphs) — large enough to be self-contained. Fetching neighbors triples the token cost per match (~712 tokens per enriched passage vs ~237 without), which exhausted the Groq TPM budget on the free tier. At this chunk size the quality trade-off does not justify the cost.

**To re-enable:** set `neighbor_window=1` in `database.py — get_agent_context()`. Each surviving match will then fetch chunks N-1 and N+1 and concatenate them in order:

```
chunk N-1 text

chunk N text   ← the semantically matched chunk

chunk N+1 text
```

---

## Prompt Assembly

All inputs are assembled in `session_service.py — build_context_prompt()`.

### With retrieved chunks

```
Discussion topic: {topic}

Relevant historical speaker context:

[1] {enriched chunk 1 text}

[2] {enriched chunk 2 text}

[3] ...

Your response must be grounded in the passages above - these are your authentic
words and thinking. Reason from the ideas and principles in those passages when
addressing the current topic. Do not draw on general or popular knowledge about
yourself beyond what the passages establish. Do not reproduce the original scene,
courtroom exchange, interview, or speech verbatim. Do not address historical
interlocutors from the source material unless they are part of this debate.
Apply the retrieved ideas directly to the current topic and panel discussion.

Recent discussion context (for awareness only — do NOT echo or mirror):
Turn 3, Socrates: ...
Turn 4, Napoleon: ...
...up to 4 turns...

Now contribute the next turn. CRITICAL: Your response must begin from your OWN
distinct perspective and voice. Do NOT open with the same framing, phrasing, or
angle as any previous speaker. Do NOT rephrase or restate what another speaker
already said before adding your view. Jump directly into your own thought — your
opening sentence must be entirely different in structure and content from any
prior turn. Keep it concise, concrete, and relevant. Do not prefix your answer
with your name, a speaker label, or a turn number. Do not import historical
addressees, scene setup, or source-only references unless the current topic
explicitly requires them.
```

### Without retrieved chunks (score threshold not met)

```
Discussion topic: {topic}

No source passages were retrieved for this turn. Respond using only the
documented philosophy, principles, and positions that define your persona.
Do not speculate beyond what is historically established.

Recent discussion context (for awareness only — do NOT echo or mirror):
...

Now contribute the next turn. ...
```

### First turn (no prior context)

When `context_messages` is empty, the recent discussion block is omitted entirely and the turn instruction reads:

```
You are taking the first turn. Provide a clear, substantive response. Do not
prefix your answer with your name, a speaker label, or a turn number. Do not
import historical addressees, scene setup, or source-only references unless
the current topic explicitly requires them.
```

---

## Full Data Flow Summary

```
Redis call 1  ──────────────────────────────────────────┐
  agent config (system prompt, model)                   │
                                                        │
Redis call 2  ──────────────────────────────────────────┤
  last 4 turns for active topic (topic-scoped)         │
  + current speaker's last turn if not in window       │
                                                        ▼
Vector call 3 ───────────────────────────────────────► raw matches
  query: topic only                                     │
  filter: agent_id = current speaker                    │
  fetch_k: 11, score threshold: 0.60                    │
  diversity: max 2 chunks per source                    │
  adaptive top_k: 5 (score ≥ 0.72) or 7 (score < 0.72) │
  final: up to 7 after filtering                        │
                                                        ▼
Vector call 4 ───────────────────────────────────────► enriched chunks
  fetch neighbors N-1 and N+1 for each match            │
  concatenate in order                                  │
                                                        ▼
build_context_prompt() ──────────────────────────────► user message
  [topic]                                               |
  [knowledge block — enriched chunks]                   |
  [retrieval guidance or no-retrieval fallback]         |
  [context block — last 4 turns, topic-scoped]         |
  [turn instructions — anti-echo, persona, format]      |
                                                        ▼
LLM call ────────────────────────────────────────────► generated turn
  system: agent system_prompt
  user:   assembled prompt above
```

---

## Key Design Decisions

**Query uses the topic only, not the live debate state.** Retrieval is anchored to what the discussion is *about*, not to what the previous speaker said. This keeps each speaker's knowledge grounding clean and prevents one speaker's vocabulary from steering another speaker's retrieval. The LLM already has full debate awareness via the 10-turn context window.

**Agent filter is structural, not soft.** The `agent_id` filter is applied at the vector index level, not as a post-processing step. There is no path by which one speaker's corpus leaks into another speaker's prompt.

**Source diversity prevents cluster retrieval.** Without capping, a speaker with a large corpus (e.g. 1,300+ chunks) would return multiple adjacent passages from the same section of the same document. The diversity filter ensures the 5 returned chunks span different parts of the corpus.

**Neighbor enrichment prevents fragment retrieval.** Pure chunk-level retrieval often hits a passage in the middle of an argument. The neighbor window ensures each retrieved passage has its surrounding context, reducing decontextualised fragments in the prompt.

**The 0.60 threshold is a hard gate.** A low-relevance chunk is worse than no chunk — it can anchor the speaker's response to an unrelated passage. If nothing scores above the threshold the system falls back to persona-only grounding with an explicit instruction in the prompt.

**Context is topic-scoped and limited to 4 turns.** `fetch_context_messages` filters history by the active topic and returns at most the last 4 turns. Changing the topic or wiping the session starts a clean context window with no carryover from previous discussions. 4 turns covers all speakers in a standard 4-speaker panel; see the known limitation on larger panels in the design decisions above.

**The current speaker's last turn is always anchored.** In panels with 5 or more speakers the 4-turn window may not include the current speaker's own last response for the same topic. The anchor mechanism fetches it separately (looking back up to 200 turns) and prepends it, so the speaker always sees their own prior position before contributing the next turn.

**Adaptive top_k compensates for weak retrieval signals.** When the best-scoring chunk scores below 0.72, the result cap expands from 5 to 7 using candidates already in the fetch pool — no extra Upstash call. This trades a marginally larger prompt for better coverage when the topic query lands in a less-dense region of the corpus.

**Model:** `llama-3.3-70b-versatile` on Groq (12K TPM free tier). The 70B model is chosen over smaller alternatives because persona fidelity — sounding like Socrates, not a generic assistant — is the core showcase value.
