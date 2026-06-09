# Backend Guide

This document is the file-by-file code map for the Python backend. It is intended to be the safest form of comprehensive backend documentation: it explains what every backend code file does, how the pieces fit together, and where to look when debugging or extending a specific behavior, without creating high-churn comment-only edits across dozens of modules.

## Architecture

The backend is a FastAPI application that coordinates four main concerns:

- API request handling and response shaping.
- Session and agent state persistence in Upstash Redis.
- speaker-grounding retrieval from Upstash Vector.
- LLM request orchestration, streaming, telemetry, and prompt capture.

At runtime, the flow is:

1. `main.py` builds the FastAPI app and installs the router modules.
2. `composition.py` wires the service graph together.
3. API route modules delegate to service modules.
4. Service modules call Redis, Upstash Vector, and the inference provider.
5. Utility modules normalize execution metrics, text metrics, and PDF export output.
6. Script modules support offline ingestion, vector inspection, and prompt inspection.

## Runtime Configuration

Runtime configuration is validated through `settings.py` before the FastAPI app is built.

Core required environment variables:

- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `UPSTASH_VECTOR_REST_URL`
- `UPSTASH_VECTOR_REST_TOKEN`
- `LLM_API_KEY`

Useful optional variables:

- `LLM_API_BASE_URL`
- `LLM_MODEL_ID`
- `LLM_429_MAX_RETRIES`
- `LLM_REQUEST_THROTTLE_SECONDS`
- `CORS_ALLOW_ORIGINS`
- `CORS_ALLOW_ORIGIN_REGEX`
- `BACKEND_STARTUP_READINESS_MODE`
- `AGENT_REGISTRY_CACHE_TTL_SECONDS`
- `AGENT_CONFIG_CACHE_TTL_SECONDS`

`BACKEND_STARTUP_READINESS_MODE` supports:

- `strict`: fail startup when Redis, Vector, or inference is offline.
- `warn`: report degraded readiness but keep serving.
- `off`: skip startup readiness checks.

## File Map

### Root modules

- `backend/main.py`
Owns the FastAPI application, request and response models, shared logging setup, startup readiness behavior, route registration, static mounting, and runtime app-state exposure. This is the best entrypoint when you need to understand the externally visible API shape or the order in which the backend boots.

- `backend/composition.py`
Builds the runtime dependency graph. This module creates Redis and Vector clients, instantiates each service with its dependencies, and returns the service registry attached to `app.state`. This is the file to inspect when you want to know where a dependency comes from or how services are wired together.

- `backend/settings.py`
Parses environment-backed settings into typed Pydantic models. This module centralizes defaults, startup validation, base directory resolution, and CORS parsing. This is the authoritative place for backend configuration semantics.

### API package

- `backend/api/__init__.py`
Package marker for the API router modules.

- `backend/api/root.py`
Defines the root and top-level metadata routes. This is the shallowest route surface and usually the first smoke-check entrypoint for the backend.

- `backend/api/agents.py`
Defines agent registry endpoints for registration and listing. These routes delegate to `AgentRegistryService` and are responsible for shaping agent registry payloads at the HTTP boundary.

- `backend/api/discussion.py`
Defines the debate-generation routes, including non-streaming and streaming turn-generation endpoints. This router delegates to `DiscussionService` and is the main HTTP entrypoint for live debate turns.

- `backend/api/sessions.py`
Defines session-history, topic, and cleanup endpoints. These routes map session-related HTTP operations to `SessionService` behavior.

- `backend/api/exports.py`
Defines transcript export endpoints, including PDF-related flows that rely on `SessionService` and `pdf_export.py`.

- `backend/api/telemetry.py`
Defines backend telemetry and health-oriented endpoints. These routes surface execution metrics and service-readiness data to the frontend or operator workflows.

### Services package

- `backend/services/__init__.py`
Package marker for the service layer.

- `backend/services/agent_registry.py`
Owns agent registry persistence and short-lived in-memory caching. It handles agent registration, agent listing, config lookup, and cache invalidation. This service sits between API routes and Redis-backed agent definitions.

- `backend/services/database.py`
Encapsulates Redis-backed session storage and Upstash Vector retrieval. It handles chat history reads and writes, telemetry snapshots, retrieval queries, neighbor enrichment, and fallback embedding logic when hosted embedding queries are unavailable.

- `backend/services/session_service.py`
Owns session-oriented formatting and storage behavior. It loads recent context turns, builds the context prompt passed to the LLM, summarizes vector telemetry, sanitizes model output, saves messages, and prepares transcript-oriented session data.

- `backend/services/turn_workflow.py`
Coordinates the shared turn lifecycle used by generation endpoints. It prepares the inputs needed for a turn, including context-aware retrieval, and finalizes a generated turn by sanitizing the message, deriving telemetry, and persisting it.

- `backend/services/discussion_service.py`
Coordinates route-level discussion flows so route handlers remain declarative. It ties together prompt building, vector telemetry summarization, provider request capture, non-streaming generation, streaming generation, and turn finalization.

- `backend/services/llm_service.py`
Owns outbound inference-provider calls. It builds provider request payloads, handles retry logic, implements request throttling and cooldown behavior, manages streaming token iteration, and normalizes provider execution metrics.

- `backend/services/observability.py`
Owns health checks, latest-metrics persistence, and local prompt-capture logging. This is the main operational introspection service for checking Redis, Vector, and inference health and for capturing exact provider requests locally.

### Utilities package

- `backend/utils/__init__.py`
Package marker for backend utility helpers.

- `backend/utils/execution_metrics.py`
Normalizes provider timing and token usage into the shared execution metrics model. This module converts raw provider payloads and headers into stable backend telemetry structures for both non-streaming and streaming requests.

- `backend/utils/text_metrics.py`
Provides lightweight lexical text similarity helpers. It currently exposes Jaccard-based entropy scoring used to compare turns or measure response divergence.

- `backend/utils/pdf_export.py`
Renders session transcripts to PDF. It handles font selection, Unicode-safe or Latin-1-safe text sanitation, page layout, transcript formatting, and temporary-file output.

### Script package

- `backend/scripts/ingest_agent_knowledge.py`
Offline ingestion pipeline for speaker RAG corpora. It resolves source files, extracts speaker-specific source documents, chunks them, builds Upstash Vector payloads, performs dry-runs, and upserts chunk batches safely. This is the main operator script for rebuilding the vector corpus.

- `backend/scripts/query_vector_stats.py`
Operator utility for querying or scanning Upstash Vector and summarizing corpus contents by agent and source. This is the safest script to inspect index state before and after ingestion.

- `backend/scripts/render_provider_prompt_example.py`
Prompt-inspection script for reconstructing or rendering provider request examples. This supports debugging prompt assembly, retrieval context, and stored local prompt captures.

### Tests package

- `backend/tests/test_api_smoke.py`
FastAPI smoke coverage for startup readiness, root routes, agent routes, generation routes, and request-id behavior.

- `backend/tests/test_agent_registry_service.py`
Unit coverage for the agent registry caching and Redis-backed registry behaviors.

- `backend/tests/test_database_service.py`
Unit coverage for Redis-backed history persistence, topic-scoped history reads, vector retrieval behavior, fallback id parsing, neighbor enrichment, and low-score retrieval filtering.

- `backend/tests/test_execution_metrics_utils.py`
Unit coverage for execution metric extraction and normalization helpers.

- `backend/tests/test_ingest_agent_knowledge.py`
Regression coverage for speaker extraction plans, chunking policies, source metadata, and ingestion-specific cleanup rules.

- `backend/tests/test_observability_service.py`
Unit coverage for health checks, prompt capture persistence, and latest execution metrics reads and writes.

- `backend/tests/test_pdf_export.py`
Unit coverage for transcript PDF generation behavior and text sanitation.

- `backend/tests/test_query_vector_stats.py`
Unit coverage for vector summary aggregation and output formatting.

- `backend/tests/test_render_provider_prompt_example.py`
Unit coverage for prompt example rendering and captured prompt inspection behavior.

- `backend/tests/test_session_service.py`
Unit coverage for context-prompt formatting, including how retrieval blocks are rendered into the prompt.

- `backend/tests/test_text_metrics.py`
Unit coverage for the Jaccard entropy and text normalization helpers.

- `backend/tests/test_turn_workflow_service.py`
Unit coverage for shared turn preparation and turn finalization, including topic-only retrieval query construction.

## Retrieval and RAG Notes

The current retrieval path spans three files:

- `services/turn_workflow.py`
Builds a topic-only vector query (`query_text = topic`). Debate awareness comes from the recent context block in the prompt, not from the retrieval query.

- `services/database.py`
Queries Upstash Vector with an `agent_id` filter, applies the score threshold (0.60), source diversity (max 2 chunks per source), adaptive top_k, and optional neighbor enrichment. Neighbor enrichment is disabled by default (`neighbor_window=0`) to control token cost.

- `services/session_service.py`
Formats retrieved chunks into numbered prompt blocks and assembles the user message with retrieval guidance and recent debate context.

See `docs/prompt-construction.md` for the full pipeline.

## Ingestion Notes

`scripts/ingest_agent_knowledge.py` follows the same high-level flow for every supported speaker:

1. Resolve the source file, usually `data/<agent-id>.txt`.
2. Run the agent's source-document extraction plan.
3. Chunk the extracted documents using the agent's chunking policy.
4. Build stable vector ids and metadata payloads.
5. Dry-run or upsert to Upstash Vector.

Operational commands:

- `python backend/scripts/ingest_agent_knowledge.py --list-agents`
- `python backend/scripts/ingest_agent_knowledge.py --describe-agent agt_014`
- `python backend/scripts/ingest_agent_knowledge.py --agent-id agt_014 --dry-run`
- `python backend/scripts/query_vector_stats.py --all-agents`
- `python backend/scripts/query_vector_stats.py --query "stoic discipline" --top-k 20`
- `python backend/scripts/query_vector_stats.py --all-agents --agent-id agt_014`

## Production Notes

What is already in place:

- typed startup configuration validation
- shared outbound HTTP client reuse
- request-scoped logging with `X-Request-ID`
- startup readiness checks
- local prompt capture for provider-request inspection
- retrieval score filtering and optional neighbor enrichment (disabled by default)
- an ingestion pipeline with dry-run support and batched Upstash writes

Operational cautions:

- Upstash Vector enforces a maximum write batch size, so ingestion now batches upserts instead of sending arbitrarily large writes.
- Full corpus rebuilds can still hit provider daily write quotas on lower-tier plans.
- Retrieval quality depends on both chunk policy and source extraction quality, so ingestion changes should always be dry-run and re-queried.

The repository includes backend CI coverage through `.github/workflows/backend-ci.yml`, which runs the backend unit suite on pushes and pull requests.