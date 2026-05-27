# Prompt Construction

This document describes exactly how the backend assembles the user prompt for each debate turn.

The system prompt (persona, voice, model config) lives on the agent record and is sent separately as the `system` role message. This document covers the `user` role message only.

---

## The Four Calls

Before a prompt can be built, the backend makes four storage calls per turn.

Calls 1 and 2 run in parallel:

| # | Store | Call | Returns |
|---|---|---|---|
| 1 | Redis | `fetch_agent_config(agent_id)` | Speaker persona, system prompt, model config |
| 2 | Redis | `fetch_context_messages(session_id, limit=5, topic)` | Last 5 turns for the active topic |
| 3 | Vector | `vector_index.query(data=query_text, filter=agent_id, top_k=4)` | Up to 4 semantically matched chunks |
| 4 | Vector | `vector_index.fetch(ids=[neighbor_ids])` | Adjacent chunks for context enrichment |

Call 3 depends on the result of call 2 (the query text uses the last message). Call 4 depends on call 3 (neighbor ids come from the query results). Calls 3 and 4 are therefore sequential.

---

## Building the Vector Query

```python
# turn_workflow.py — prepare_turn_inputs()
if previous_response:
    query_text = f"{topic}. {previous_response[:200]}"
else:
    query_text = topic
```

`previous_response` is the last message in the context window, regardless of which speaker said it.

The query is therefore shaped by the current topic **plus the most recent argument made in the room**. This means each speaker's retrieval is biased toward whatever was just said — the RAG is live-debate-aware, not purely topic-driven.

On the first turn of a session there is no previous response, so the query is the topic alone.

The 200-character cap is a raw slice. It is used only as a retrieval signal; the full previous response text is still injected into the prompt separately as part of the context block.

---

## Chunk Selection

Selection happens in three layers inside `database.py — get_agent_context()`.

### Layer 1 — Agent filter

```python
filter_expression = f"agent_id = '{agent_id}'"
```

Applied at the vector index level before any scoring. A speaker can only retrieve chunks from their own corpus. Cross-agent contamination is structurally impossible.

### Layer 2 — Semantic ranking

```python
results = self.vector_index.query(
    data=query_text,
    top_k=4,
    filter=filter_expression,
    include_data=True,
)
```

Upstash Vector embeds the query text server-side and returns the top 4 chunks by cosine similarity from that agent's namespace.

### Layer 3 — Score threshold

```python
_VECTOR_SCORE_THRESHOLD = 0.60

matches = [m for m in matches if (m.get("score") or 0.0) >= 0.60]
```

Any chunk scoring below 0.60 is dropped. If all four candidates fall below the threshold, the match list is empty and the prompt falls back to the no-retrieval path (see below).

---

## Neighbor Enrichment

After scoring, each surviving match is enriched with its adjacent chunks.

```python
# neighbor_window = 1
# For a match at chunk index N, fetch N-1 and N+1

for offset in range(-1, 2):           # -1, 0, +1
    neighbor_ids.append(
        chunk_id(agent_id, source_slug, chunk_index + offset)
    )
```

The matched chunk and its neighbors are then concatenated in order and treated as a single passage:

```
chunk N-1 text

chunk N text   ← the semantically matched chunk

chunk N+1 text
```

This prevents the LLM from receiving a fragment mid-argument. The neighbor window gives the matched passage its surrounding reading context without requiring a larger `top_k`.

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
  agent config (system prompt, model)                    │
                                                         ▼
Redis call 2  ──────────────────────────────────────► build query_text
  last 5 turns for active topic                          │
  ↳ previous_response = last message in window           │
                                                         ▼
Vector call 3 ───────────────────────────────────────► raw matches
  query: topic + previous_response[:200]                 │
  filter: agent_id = current speaker                     │
  top_k: 4, score threshold: 0.60                        │
                                                         ▼
Vector call 4 ───────────────────────────────────────► enriched chunks
  fetch neighbors N-1 and N+1 for each match             │
  concatenate in order                                   │
                                                         ▼
build_context_prompt() ─────────────────────────────► user message
  [topic]
  [knowledge block — enriched chunks]
  [retrieval guidance or no-retrieval fallback]
  [context block — last N turns]
  [turn instructions — anti-echo, persona, format]
                                                         ▼
LLM call ────────────────────────────────────────────► generated turn
  system: agent system_prompt
  user:   assembled prompt above
```

---

## Key Design Decisions

**Query uses the last message, not just the topic.** Each speaker's retrieval is shaped by the live debate state. If Napoleon just argued about centralized power, Socrates's retrieval will be biased toward passages about governance — making the conversation more responsive.

**Agent filter is structural, not soft.** The `agent_id` filter is applied at the vector index level, not as a post-processing step. There is no path by which one speaker's corpus leaks into another speaker's prompt.

**Neighbor enrichment prevents fragment retrieval.** Pure chunk-level retrieval often hits a passage in the middle of an argument. The neighbor window ensures each retrieved passage has its surrounding context, reducing decontextualised fragments in the prompt.

**The 0.60 threshold is a hard gate.** A low-relevance chunk is worse than no chunk — it can anchor the speaker's response to an unrelated passage. If nothing scores above the threshold the system falls back to persona-only grounding with an explicit instruction in the prompt.
