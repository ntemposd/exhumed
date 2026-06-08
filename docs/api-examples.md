# API Examples

These examples document the current backend request and response shapes that matter most for local development and frontend integration.

## `GET /agents`

Example response:

```json
{
  "agents": [
    {
      "agent_id": "agt_001",
      "display_name": "Socrates",
      "system_prompt": "You are Socrates...",
      "temperature": 0.7,
      "max_tokens": 512
    }
  ]
}
```

## `POST /process-turn`

Example request:

```json
{
  "session_id": "bfcd1c11-7e60-422f-87bf-f56975b0d527",
  "topic": "How should power answer for the lives it reshapes?",
  "agent_id": "agt_001",
  "temperature": 0.7,
  "turn_number": 1
}
```

Example response:

```json
{
  "message_id": "7a6cdd1d-f879-4b02-b40c-79e887f460c3",
  "agent_id": "agt_001",
  "display_name": "Socrates",
  "message": "If power reshapes lives, should it not first answer what good it claims to serve?",
  "turn_number": 1,
  "created_at": "2026-05-01T00:41:57.248092+00:00",
  "telemetry": {
    "entropy": 0.0,
    "latency_ms": 842,
    "word_count": 18,
    "vector": {
      "used": true,
      "match_count": 4,
      "top_score": 0.781,
      "sources": ["Apology"],
      "chunk_ids": [
        "agt_001:apology:0007",
        "agt_001:apology:0018"
      ],
      "context_chars": 3121
    }
  },
  "execution_metrics": {
    "generation_duration_ms": 690,
    "prompt_tokens": 502,
    "completion_tokens": 44,
    "total_tokens": 546,
    "tokens_per_second": 63.8,
    "queue_time_ms": 31,
    "prompt_time_ms": 96,
    "ttft_ms": 214,
    "network_rtt_ms": 842,
    "provider": "llm",
    "updated_at": "2026-05-01T00:41:57.248092+00:00"
  }
}
```

## `POST /process-turn/stream`

Example request:

```json
{
  "session_id": "bfcd1c11-7e60-422f-87bf-f56975b0d527",
  "topic": "How should power answer for the lives it reshapes?",
  "agent_id": "agt_002",
  "temperature": 0.7,
  "turn_number": 2
}
```

Streamed response uses the Vercel AI SDK data stream protocol (`text/plain; charset=utf-8`, `x-vercel-ai-data-stream: v1`):

```
0:"I think"
0:" the real question"
8:[{"type":"status","stage":"retrying","message":"Rate limit hit. Retrying in 2.0s"}]
2:[{...final turn object...}]
d:{"finishReason":"stop","usage":{"promptTokens":502,"completionTokens":44}}
```

- `0:` — incremental text token
- `8:` — status annotation (rate-limit retry, error)
- `2:` — final turn metadata (message_id, telemetry, execution_metrics)
- `d:` — finish signal with token usage

Final `2:` data payload:

```json
{
  "type": "final",
  "message_id": "93a528a1-1a98-40e4-a1a0-81ea0216602e",
  "agent_id": "agt_002",
  "display_name": "Steve Jobs",
  "message": "You have to start by asking what kind of human future the system is optimizing for.",
  "turn_number": 2,
  "created_at": "2026-05-01T00:43:12.908413+00:00",
  "telemetry": {
    "entropy": 0.74,
    "latency_ms": 803,
    "word_count": 15,
    "vector": {
      "used": true,
      "match_count": 4,
      "top_score": 0.823,
      "sources": ["Stanford Commencement Address"],
      "chunk_ids": [
        "agt_002:stanford_commencement:0008"
      ],
      "context_chars": 2780
    }
  },
  "execution_metrics": {
    "generation_duration_ms": 611,
    "prompt_tokens": 471,
    "completion_tokens": 36,
    "total_tokens": 507,
    "tokens_per_second": 58.92,
    "queue_time_ms": 28,
    "prompt_time_ms": 101,
    "ttft_ms": 198,
    "network_rtt_ms": 803,
    "provider": "llm",
    "updated_at": "2026-05-01T00:43:12.908413+00:00"
  }
}
```

## `POST /generate`

Legacy non-streaming endpoint. `previous_response` is used to calculate the Jaccard entropy score in the telemetry response — it is compared against the generated response to produce the debate diversity metric. It is not used to build the RAG query; the query uses the topic only.

Example request:

```json
{
  "session_id": "bfcd1c11-7e60-422f-87bf-f56975b0d527",
  "topic": "What should great work optimize for?",
  "agent_id": "agt_002",
  "previous_response": "Power should answer for consequences, not merely intentions."
}
```

Example response:

```json
{
  "response": "Great work has to optimize for meaning as much as output.",
  "telemetry": {
    "entropy": 0.81,
    "latency_ms": 756,
    "word_count": 10,
    "vector": {
      "used": true,
      "match_count": 4,
      "top_score": 0.817,
      "sources": ["Stanford Commencement Address"],
      "chunk_ids": [
        "agt_002:stanford_commencement:0004"
      ],
      "context_chars": 2540
    }
  },
  "message_id": "e303a17c-a6a8-4f22-92f6-b616e83b1d74",
  "turn_number": 3
}
```

## `POST /chat/stream`

Example request:

```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Summarize the debate so far."}
  ],
  "agent_id": "agt_001",
  "session_id": "bfcd1c11-7e60-422f-87bf-f56975b0d527",
  "topic": "How should power answer for the lives it reshapes?",
  "temperature": 0.7,
  "save_response": true
}
```

Response format:

- plain streamed text chunks
- no NDJSON wrapper

## `GET /services-status`

Example response:

```json
{
  "status": "ok",
  "services": [
    {"name": "Redis", "status": "ONLINE", "latency_ms": 42, "detail": null},
    {"name": "Vector", "status": "ONLINE", "latency_ms": 51, "detail": null},
    {"name": "LLM", "status": "ONLINE", "latency_ms": 183, "detail": null}
  ],
  "checked_at": "2026-05-01T00:46:14.174503+00:00"
}
```

## `GET /telemetry/latest`

Example response:

```json
{
  "status": "ok",
  "metrics": {
    "generation_duration_ms": 690,
    "prompt_tokens": 502,
    "completion_tokens": 44,
    "total_tokens": 546,
    "tokens_per_second": 63.8,
    "queue_time_ms": 31,
    "prompt_time_ms": 96,
    "ttft_ms": 214,
    "network_rtt_ms": 842,
    "provider": "llm",
    "updated_at": "2026-05-01T00:41:57.248092+00:00"
  }
}
```

## `GET /sessions/{session_id}/topic`

Example response:

```json
{
  "session_id": "bfcd1c11-7e60-422f-87bf-f56975b0d527",
  "topic": "How should power answer for the lives it reshapes?"
}
```

## `POST /agents/register`

Example request:

```json
{
  "agent_id": "agt_017",
  "display_name": "Virginia Woolf",
  "system_prompt": "You are Virginia Woolf. You respond in reflective, psychologically precise prose.",
  "temperature": 0.7,
  "max_tokens": 512
}
```

Example response:

```json
{
  "status": "ok",
  "agent_id": "agt_017"
}
```