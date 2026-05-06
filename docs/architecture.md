# Architecture

This document describes how EXHUMED works today.

## Runtime Overview

The live request path is:

- Next.js frontend -> FastAPI backend -> LLM provider
- Redis stores session messages, session topic, and session telemetry snapshots
- Vector stores historical knowledge chunks for each speaker
- each debate turn can retrieve speaker-specific knowledge from Vector and inject it into the prompt

## Core Components

### Backend

The orchestration layer lives in `backend/main.py`.

Key responsibilities:

- load and cache agent definitions from Redis
- manage session topics and ordered debate history
- build prompts for each turn
- call the configured LLM provider
- stream or return model outputs
- persist completed turns back to Redis
- emit execution and retrieval telemetry
- export transcript PDFs

### Service Layer

The storage abstraction lives in `backend/services/database.py`.

Current responsibilities:

- read and write session history in Redis
- persist session-level entropy metrics
- query Upstash Vector with agent-scoped filters
- return retrieval matches in a normalized format

### Historical Ingestion

Historical source ingestion lives in `backend/scripts/ingest_agent_knowledge.py`.

Current supported sources:

- `agt_001` -> Socrates, from `data/agt_001.txt`
- `agt_002` -> Steve Jobs, from `data/agt_002.txt`

The script performs:

- source-specific body extraction
- chunking with overlap
- deterministic vector id creation
- Upstash Vector upsert with metadata

### Active Frontend

The active UI is the Next.js app in `frontend/`.

Current capabilities:

- topic editing
- council drafting / speaker selection
- streaming debate turns
- transcript rendering
- right-side telemetry panel
- Vector usage visibility by turn
- transcript PDF export via backend

## Storage Roles

### Redis

Redis is the canonical live state store.

Current usage:

- `session:{session_id}:messages`
- `session:{session_id}:topic`
- `session:{session_id}:telemetry`
- agent registry keys and indexes

Redis stores live debate state. It is not being replaced by Vector.

### Vector

Vector is used for speaker knowledge retrieval.

Current usage:

- stores historical chunks tagged with `agent_id`
- queried per turn using the current topic text
- filtered to the active speaker with metadata filtering

Vector does not currently store live debate messages.

## Turn Lifecycle

For each turn the backend currently does the following:

1. Load the speaker config from Redis.
2. Load recent context messages from Redis.
3. Query Vector for speaker-specific historical context.
4. Summarize Vector telemetry for the turn.
5. Build the prompt from:
   - system prompt
   - current topic
   - retrieved historical context
   - recent discussion context
6. Call the LLM provider.
7. Persist the finished turn back into Redis.
8. Return execution metrics and turn telemetry to the frontend.

## Retrieval Behavior

Retrieval is currently:

- topic-driven
- speaker-filtered
- capped by the backend `top_k` used for `get_agent_context_matches()`

The backend also adds prompt-side guardrails so retrieved text is treated as historical grounding rather than a scene to continue directly. This prevents issues like Socrates incorrectly addressing Meletus in unrelated debates.

## Telemetry Model

### Execution Metrics

Per-turn execution metrics include:

- generation duration
- prompt tokens
- completion tokens
- total tokens
- tokens per second
- queue time
- prompt time
- time to first token
- network RTT

### Debate Metrics

Per-turn debate telemetry includes:

- Jaccard entropy versus the previous response
- latency
- word count
- Vector retrieval telemetry

### Retrieval Telemetry

The system tracks retrieval details per turn, including:

- match count
- top score
- sources represented
- chunk ids
- injected context size

The frontend currently renders a simplified summary in the `VECTOR USAGE` section.

## Backends and Frontends in the Repo

### Active

- `backend/` -> FastAPI
- `frontend/` -> Next.js 15 + React 19

## Dependencies

### Backend

Defined in `backend/requirements.txt`:

- `fastapi`
- `uvicorn[standard]`
- `groq`
- `python-dotenv`
- `httpx`
- `upstash-redis`
- `upstash-vector`
- `sentence-transformers`
- `fpdf2`

### Next.js Frontend

Defined in `frontend/package.json`:

- `next`
- `react`
- `react-dom`
- `ai`
- `typescript`

## Current Limitations

- historical ingestion is not yet generalized for all speakers
- some source extraction logic is speaker-specific
- Docker Compose does not currently launch the Next.js frontend
- retrieval influence is observable through telemetry and output comparison, not as a strict causal percentage

## Validation Surfaces

Current lightweight validation includes:

- `test_jaccard.py`
- `python -m py_compile backend/main.py`
- direct retrieval smoke tests through `backend.services.database.create_database_service()`