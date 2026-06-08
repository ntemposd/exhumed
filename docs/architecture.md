# Architecture

This document describes how EXHUMED works today.

## Runtime Overview

The live request path is:

- Next.js frontend → FastAPI backend → LLM provider
- Redis stores session messages, session topic, and session telemetry snapshots
- Upstash Vector stores historical knowledge chunks for each speaker
- Each debate turn retrieves speaker-specific knowledge from Vector and injects it into the prompt

## Core Components

### Backend

The orchestration layer lives in `backend/main.py`.

Key responsibilities:

- load and cache agent definitions from Redis
- manage session topics and ordered debate history
- build prompts for each turn
- call the configured LLM provider (Groq)
- stream or return model outputs via Vercel AI SDK data stream protocol
- persist completed turns back to Redis
- emit execution and retrieval telemetry
- export transcript PDFs

### Service Layer

| File | Responsibility |
|---|---|
| `services/database.py` | Redis session state, Upstash Vector retrieval, source diversity, adaptive top_k |
| `services/session_service.py` | Context fetching, prompt assembly, telemetry summarization |
| `services/turn_workflow.py` | Turn lifecycle: config fetch, context load, RAG query, finalization |
| `services/discussion_service.py` | Route-level coordination: process-turn, streaming, generate, chat |
| `services/llm_service.py` | Outbound LLM calls, retry policy, throttling, streaming |
| `services/agent_registry.py` | Agent config CRUD against Redis |
| `services/observability.py` | Service health checks (Redis, Vector, LLM) |
| `utils/text_metrics.py` | Jaccard entropy for debate diversity telemetry |
| `utils/execution_metrics.py` | Token counts, latency, TTFT from provider responses |
| `utils/pdf_export.py` | Transcript PDF generation |

### Historical Ingestion

Historical source ingestion lives in `backend/scripts/ingest_agent_knowledge.py`.

The script is speaker-aware: each speaker has a named `AgentIngestPlan` with a source extractor, chunking policy, and metadata config. Plans are keyed by agent id.

Current speaker corpus status:

| Agent ID | Speaker | Status |
|---|---|---|
| agt_001 | Socrates | Ingested |
| agt_002 | Steve Jobs | Ingested |
| agt_003 | Sun Tzu | Ingested |
| agt_004 | Napoleon Bonaparte | Ingested (1,318 chunks — large corpus) |
| agt_005 | Marcus Aurelius | Ingested |
| agt_006 | Cleopatra | Ingested |
| agt_007 | Leonardo da Vinci | Ingested |
| agt_008 | Ada Lovelace | Ingested (79 chunks — thin corpus) |
| agt_009 | Marie Curie | Ingested |
| agt_010 | Jorge Luis Borges | Pending — no source file |
| agt_011 | Leon Trotsky | Ingested |
| agt_012 | Friedrich Nietzsche | Ingested |
| agt_013 | Nikola Tesla | Ingested |
| agt_014 | Marie Antoinette | Ingested (1,439 chunks) |
| agt_015 | (planned) | Pending — no source file |
| agt_016 | (planned) | Pending — no source file |

The ingestion script performs:

- source-specific body extraction (removes boilerplate, license text, index pages)
- paragraph-first chunking with configurable overlap
- deterministic vector id creation (`agent_id:source_slug:NNNN`)
- Upstash Vector upsert with metadata (`agent_id`, `source_slug`, `chunk_index`, `source_title`)

### Active Frontend

The active UI is the Next.js app in `frontend/`.

Current capabilities:

- topic editing with per-topic session isolation
- council drafting and speaker selection (up to 16 speakers)
- streaming debate turns via Vercel AI SDK
- transcript rendering with per-turn telemetry chips
- right-side telemetry panel (vector usage, execution metrics, debate diversity)
- dark / light theme toggle
- transcript PDF export via backend
- Buy Me a Coffee integration via navbar

## Storage Roles

### Redis

Redis is the canonical live state store.

Current key structure:

- `session:{session_id}:messages` — ordered list of serialized turn objects
- `session:{session_id}:topic` — active topic string
- `session:{session_id}:telemetry` — latest entropy snapshot

Redis stores live debate state only. It is not used for speaker knowledge.

### Upstash Vector

Vector is used for speaker knowledge retrieval only.

Current usage:

- stores historical chunks tagged with `agent_id`, `source_slug`, `chunk_index`
- queried per turn using the current topic as the query text
- filtered at the index level to the active speaker with a metadata filter
- speaker knowledge is never cross-contaminated — the agent filter is structural

Vector does not store live debate messages.

## Turn Lifecycle

For each turn the backend does the following:

1. Load the speaker config from Redis (concurrently with step 2).
2. Load the last 4 context turns from Redis, topic-scoped. If the panel has 5 or more speakers, also fetch and prepend the current speaker's own last turn (anchor mechanism).
3. Query Upstash Vector with the topic text as the query. Fetch 11 candidates, apply score threshold (0.60), apply source diversity filter (max 2 chunks per source), apply adaptive top_k (5 if top score ≥ 0.72, otherwise 7).
4. Build the prompt from: system prompt, topic, retrieved knowledge block, retrieval guidance, context turns, turn instructions.
5. Call the LLM provider (Groq, `llama-3.3-70b-versatile`).
6. Persist the finished turn to Redis, update telemetry, emit execution metrics.
7. Stream or return the response to the frontend.

## Retrieval Behavior

Retrieval is:

- **topic-driven** — query text is the discussion topic only. The previous speaker's response is not mixed into the query; it is already visible to the LLM via the context block.
- **speaker-filtered** — `agent_id` filter applied at the vector index level before scoring
- **diversity-filtered** — at most 2 chunks returned from any single source document
- **adaptively sized** — returns 5 chunks on strong queries (top score ≥ 0.72), 7 on weak queries
- **neighbor enrichment disabled** — chunks are large enough (~950 chars) to be self-contained; enrichment tripled token cost and exhausted Groq free-tier TPM

The current speaker's own last turn is always injected into the context via the anchor mechanism (see `fetch_context_messages`), so the speaker always reasons from their own prior position before responding. The previous speaker's most recent response (`context_messages[-1]`) is passed to `calculate_entropy()` after generation to produce the DEBATE DIVERSITY metric — it is not used in retrieval.

See `docs/prompt-construction.md` for the full retrieval pipeline and prompt assembly details.

## Telemetry Model

### Execution Metrics

Per-turn execution metrics (from Groq response headers and timing):

- generation duration ms
- prompt tokens
- completion tokens
- total tokens
- tokens per second
- queue time ms
- prompt time ms
- time to first token ms
- network RTT ms

### Debate Metrics

Per-turn debate telemetry:

- Jaccard entropy versus the previous speaker's response (0 = identical, 1 = fully divergent)
- latency ms
- word count
- vector retrieval telemetry

### Retrieval Telemetry

Tracked per turn and surfaced in the `VECTOR USAGE` section of the frontend sidebar:

- match count
- top score
- sources represented
- chunk ids
- injected context size (chars)

## Dependencies

### Backend (`backend/requirements.txt`)

- `fastapi`
- `uvicorn[standard]`
- `httpx`
- `python-dotenv`
- `upstash-redis`
- `upstash-vector`
- `sentence-transformers` (local BGE fallback only)
- `fpdf2`

### Frontend (`frontend/package.json`)

- `next` (15)
- `react` (19)
- `react-dom`
- `ai` (Vercel AI SDK)
- `typescript`
- `@vercel/analytics`

## LLM Provider

**Model:** `llama-3.3-70b-versatile` on Groq.
**Free tier limit:** 12,000 tokens per minute (TPM).
**Why 70B over smaller models:** persona fidelity — sounding like Socrates, not a generic assistant — is the core showcase value. The 70B model handles character voice significantly better than 8B alternatives.

The backend also supports any OpenAI-compatible provider via `LLM_API_BASE_URL` and `LLM_API_KEY` environment variables.

## Current Limitations

- ingestion pipeline is speaker-aware rather than fully generic; new speakers need a named `AgentIngestPlan`
- neighbor enrichment is disabled due to Groq free-tier TPM constraints
- Napoleon's corpus is disproportionately large (1,318 chunks, ~28% of the total index); source diversity filter mitigates this at retrieval time
- Ada Lovelace has a thin corpus (79 chunks from 2 sources); retrieval coverage is weaker on broad topics
- Borges, agt_015, and agt_016 have no source material yet

## Validation

Backend tests live in `backend/tests/` and cover:

- `test_database_service.py` — Redis and Vector service logic
- `test_session_service.py` — context fetching, prompt assembly
- `test_turn_workflow_service.py` — turn lifecycle
- `test_discussion_service.py` — route-level coordination
- `test_llm_service.py` — provider calls and retry logic
- `test_text_metrics.py` — Jaccard entropy calculation
- `test_agent_registry_service.py` — agent config CRUD
- `test_execution_metrics_utils.py` — token and latency parsing
- `test_ingest_agent_knowledge.py` — chunking and extraction logic
- `test_api_smoke.py` — end-to-end route smoke tests
- `test_pdf_export.py` — transcript PDF generation
