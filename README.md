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

### 1. Configure backend `.env`

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

### 2. Configure frontend `.env.local`

The browser never calls the FastAPI backend directly. All frontend requests go through the Next.js proxy at `/api/backend`, which forwards server-side to the real backend and injects `BACKEND_API_KEY` when set.

Create `frontend/.env.local` with:

```dotenv
BACKEND_URL=http://localhost:8000
BACKEND_API_KEY=
```

For production (for example Vercel), set the same variables in the frontend host environment:

- `BACKEND_URL` must point at the deployed backend origin (for example your Railway URL).
- `BACKEND_API_KEY` must match `BACKEND_API_KEY` on the backend when API-key auth is enabled.

Generate a shared secret once, for example with `openssl rand -hex 32`, then paste the same value into Railway (`BACKEND_API_KEY`) and Vercel (`BACKEND_API_KEY`).

In Vercel, enable these variables for **both Production and Preview**. Branch preview deployments will not load speakers if Preview is missing `BACKEND_URL`, if `BACKEND_URL` still points at `localhost`, or if `BACKEND_API_KEY` does not match Railway.

If a preview URL shows Vercel "Authentication Required" on `/api/backend/*`, either sign into the preview deployment in the browser or adjust Deployment Protection in the Vercel project settings.

These are server-only variables. Do not use `NEXT_PUBLIC_BACKEND_URL`; it is not read by the current frontend.

CORS on the backend mainly matters for local direct API testing. In production the browser only talks to the Next.js origin.

### 3. Install dependencies

Windows:

```bat
setup.bat
```

macOS / Linux:

```bash
./setup.sh
```

These scripts install backend Python dependencies and the active Next.js frontend dependencies.

### 4. Run the backend

Windows:

```bat
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

macOS / Linux:

```bash
./.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Run the active frontend

```bash
cd frontend
npm install
npm run dev
```

Production frontend builds fail fast when `BACKEND_URL` is missing. At runtime, a missing value also returns `503 Backend not configured.` from the `/api/backend` proxy instead of silently failing.

Frontend runtime behavior has also been hardened so backend failures now surface clearer messages for:

- backend unreachable or incorrect `BACKEND_URL`
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
