# EXHUMED

EXHUMED is a Redis-backed, Vector-augmented multi-agent debate system where historical personas debate a shared topic while the app tracks inference, diversity, and retrieval telemetry in real time.

## What It Is

The current runtime stack is:

- FastAPI backend in `backend/`
- active Next.js frontend in `frontend/`
- Upstash Redis for live session state and agent registry
- Upstash Vector for speaker-specific historical knowledge retrieval
- OpenAI-compatible inference provider, currently configured for Groq

## Start Here

- Current architecture and runtime behavior: `docs/architecture.md`
- API payload examples: `docs/api-examples.md`
- How to add a new speaker source: `docs/adding-speakers.md`

## Quick Start

### 1. Configure `.env`

Create a repo-root `.env` with at least:

```dotenv
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...
UPSTASH_VECTOR_REST_URL=...
UPSTASH_VECTOR_REST_TOKEN=...
LLM_API_KEY=...
LLM_API_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL_ID=llama-3.1-8b-instant
```

### 2. Install dependencies

Windows:

```bat
setup.bat
```

macOS / Linux:

```bash
./setup.sh
```

These scripts install backend Python dependencies and the active Next.js frontend dependencies.

### 3. Run the backend

Windows:

```bat
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

macOS / Linux:

```bash
./.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Run the active frontend

```bash
cd frontend
npm install
npm run dev
```

App URLs:

- backend: `http://localhost:8000`
- Next.js frontend: `http://localhost:3000`

## Repository Layout

```text
backend/                     FastAPI app, service layer, ingestion scripts
frontend/                    Active Next.js frontend
data/                        Historical source documents for speakers
static/                      Shared static assets
docs/                        Current architecture and usage docs
docker-compose.yml           Backend Docker setup
```

## Current Highlights

- Redis is the canonical store for live session state.
- Vector stores historical source chunks for each speaker.
- Each debate turn can retrieve speaker-specific context from Vector.
- The Next.js telemetry sidebar shows execution, token, diversity, and Vector usage metrics.
- Prompt construction now guards against continuing source scenes verbatim.

## Notes

- The Next.js frontend is the most up-to-date client.
- Docker Compose currently starts only the backend. Run the Next.js app separately from `frontend/`.
- Historical ingestion is currently implemented for multiple speakers. See `backend/README.md` for the current backend module map and per-speaker ingestion plan.
