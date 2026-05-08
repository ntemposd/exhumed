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
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

For production frontend builds, `NEXT_PUBLIC_BACKEND_URL` must point at the deployed backend origin.
If frontend and backend run on different origins, the backend must also allow the deployed frontend origin via `CORS_ALLOW_ORIGINS` or a compatible `CORS_ALLOW_ORIGIN_REGEX`.

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

Production frontend builds now fail fast if `NEXT_PUBLIC_BACKEND_URL` is missing, which prevents silently shipping a frontend that still points at `localhost`.

Frontend runtime behavior has also been hardened so backend failures now surface clearer messages for:

- backend unreachable or bad public URL
- non-200 backend responses with JSON error payloads
- debate turns that are taking longer than usual

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

## Production Readiness

The backend is in reasonable shape for production deployment of the current architecture, but I would still treat it as "ready with caveats" rather than "fully hardened".

What is already in place:

- typed backend settings validation at startup
- startup readiness checks for Redis, Vector, and inference
- shared HTTP client reuse for inference and observability traffic
- request correlation with `X-Request-ID`
- passing backend test suite

What still remains before I would call it fully hardened:

- deeper streaming-path regression coverage
- deployment-time monitoring, alerting, and log retention in the hosting platform
- explicit production frontend deployment validation alongside the backend

The repository now includes backend CI coverage via `.github/workflows/backend-ci.yml`, so backend test execution no longer depends on manual discipline alone.

If you deploy today with the required secrets present and stable external providers, the backend should behave correctly. The main residual risk is operational discipline, not a known failing backend code path.

## Notes

- The Next.js frontend is the most up-to-date client.
- Docker Compose currently starts only the backend. Run the Next.js app separately from `frontend/`.
- `docker-compose.yml` now uses the current `LLM_*` environment variables and runs the backend without `--reload`, which makes it a safer starting point for non-dev container runs.
- Historical ingestion is currently implemented for multiple speakers. See `backend/README.md` for the current backend module map and per-speaker ingestion plan.
