# Backend Guide

This backend has three code surfaces:

- `main.py`: FastAPI application entrypoint, API routes, request orchestration, telemetry shaping, and response formatting.
- `settings.py`: typed runtime configuration loader for env-backed backend settings.
- `services/database.py`: Redis and Vector access layer for chat history, telemetry snapshots, and retrieval-backed prompt context.
- `services/agent_registry.py`: agent registry reads/writes, cache invalidation, and cached agent listing/config lookup.
- `services/turn_workflow.py`: shared turn preparation and turn finalization used by the generation endpoints.
- `scripts/ingest_agent_knowledge.py`: offline ingestion pipeline that converts speaker source texts into Upstash Vector payloads.

## Runtime Flow

`main.py` handles request validation, conversation state, retrieval, provider calls, and telemetry emission.

- Session history is stored in Upstash Redis.
- Speaker context is retrieved from Upstash Vector.
- The database service owns persistence and retrieval details so route handlers stay thin.

## Configuration

Runtime configuration is validated through `settings.py` before the FastAPI app is built.

Core required settings:

- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `UPSTASH_VECTOR_REST_URL`
- `UPSTASH_VECTOR_REST_TOKEN`
- `LLM_API_KEY`

Useful optional settings:

- `LLM_API_BASE_URL`
- `LLM_MODEL_ID`
- `LLM_429_MAX_RETRIES`
- `LLM_REQUEST_THROTTLE_SECONDS`
- `CORS_ALLOW_ORIGINS`
- `CORS_ALLOW_ORIGIN_REGEX`
- `BACKEND_STARTUP_READINESS_MODE`

`BACKEND_STARTUP_READINESS_MODE` supports:

- `strict`: fail startup when Redis, Vector, or inference is offline
- `warn`: log degraded startup but keep the app alive
- `off`: skip the startup readiness probe

## Service Layer

`services/database.py` is responsible for:

- writing and reading ordered session history in Redis
- storing short-lived telemetry snapshots in Redis
- querying Upstash Vector with hosted embeddings when available and local embeddings as a fallback
- building the retrieval-augmented system prompt block used by the model provider

## Ingestion Script

`scripts/ingest_agent_knowledge.py` now follows the same steps for every speaker:

1. Resolve the source file. By default this is `data/<agent-id>.txt`.
2. Run the speaker's extraction plan to isolate the source text that should be indexed.
3. Run the speaker's chunking plan to split the text into retrievable units.
4. Build Upstash Vector payloads with consistent metadata.
5. Preview or upsert the chunks.

Useful operator commands:

- `python backend/scripts/ingest_agent_knowledge.py --list-agents`
- `python backend/scripts/ingest_agent_knowledge.py --describe-agent agt_013`
- `python backend/scripts/ingest_agent_knowledge.py --agent-id agt_013 --dry-run`
- `python backend/scripts/query_vector_stats.py --all-agents`
- `python backend/scripts/query_vector_stats.py --query "stoic discipline" --top-k 20`
- `python backend/scripts/query_vector_stats.py --query "innovation" --agent-id agt_013 --json`

### Speaker Plans

- `agt_001` Socrates: extracts `Apology` and `Crito`, then uses default paragraph chunking.
- `agt_002` Steve Jobs: extracts the leading Stanford block plus later dashed source segments, then uses default paragraph chunking.
- `agt_003` Sun Tzu: extracts the handbook body and chunks by chapter and numbered sections.
- `agt_005` Marcus Aurelius: extracts the selected books and uses default paragraph chunking.
- `agt_007` Leonardo da Vinci: extracts the main body before bibliography/reference appendices and uses default paragraph chunking.
- `agt_011` Leon Trotsky: removes site-navigation noise, keeps the chapter body, and chunks by chapter heading.
- `agt_012` Friedrich Nietzsche: extracts selected sections and uses banded structured chunking for aphorism groups.
- `agt_013` Nikola Tesla: extracts the autobiography body and chunks by roman-numeral section headings.

## Tests

Focused backend tests currently live in `backend/tests/`.

- `test_database_service.py` covers Redis-backed history persistence behavior.
- `test_agent_registry_service.py` covers cached agent lookup, registration, and registry loading behavior.
- `test_api_smoke.py` covers endpoint smoke tests against the FastAPI app with external boundaries patched.
- `test_ingest_agent_knowledge.py` covers speaker-plan resolution, source-file resolution, extraction cleanup, and structured chunking.
- `test_query_vector_stats.py` covers query-result aggregation and report formatting for the Vector stats script.
- `test_turn_workflow_service.py` covers shared turn preparation and finalization behavior used by the generation endpoints.

## Production Notes

The backend is close to production-ready for the current single-service deployment shape.

What is now in place:

- typed startup configuration validation
- shared outbound HTTP client reuse
- request-scoped logging with `X-Request-ID`
- startup readiness checks
- backend test suite passing

What still deserves attention before a broader production rollout:

- focused streaming-path regression tests beyond smoke coverage
- CI gates so deploys always run the backend suite automatically
- observability and alerting in the target hosting environment
- rate, latency, and failure monitoring for the configured inference provider

The repository now includes a backend CI workflow at `.github/workflows/backend-ci.yml` that runs `python -m unittest discover -s backend/tests` on pushes and pull requests.