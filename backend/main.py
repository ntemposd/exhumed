"""
EXHUMED: FastAPI Backend
Decoupled AI discussion platform with dynamic agent registry.

Storage stack:
- Upstash Redis: agent registry and ordered session message index
- Upstash Vector: discussion message vectors for semantic retrieval
"""

import asyncio
import contextvars
from contextlib import asynccontextmanager
from functools import partial
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Literal, Optional
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from upstash_redis import Redis
from upstash_vector import Index

try:
    from backend.composition import build_runtime_services
    from backend.settings import BackendSettings, load_settings
    from backend.api.agents import create_agent_router
    from backend.api.discussion import create_discussion_router
    from backend.api.exports import create_export_router
    from backend.api.root import create_root_router
    from backend.api.sessions import create_session_router
    from backend.api.telemetry import create_telemetry_router
    from backend.services.agent_registry import AgentRegistryService
    from backend.services.database import DatabaseService, SentenceTransformerEmbeddingProvider
    from backend.services.discussion_service import DiscussionService
    from backend.services.llm_service import LLMService
    from backend.services.observability import ObservabilityService
    from backend.services.session_service import SessionService
    from backend.services.turn_workflow import TurnWorkflowService
    from backend.utils.execution_metrics import build_stream_execution_metrics, extract_execution_metrics
    from backend.utils.pdf_export import export_session_pdf
    from backend.utils.text_metrics import calculate_jaccard_entropy
except ModuleNotFoundError:
    from composition import build_runtime_services
    from settings import BackendSettings, load_settings
    from api.agents import create_agent_router
    from api.discussion import create_discussion_router
    from api.exports import create_export_router
    from api.root import create_root_router
    from api.sessions import create_session_router
    from api.telemetry import create_telemetry_router
    from services.agent_registry import AgentRegistryService
    from services.database import DatabaseService, SentenceTransformerEmbeddingProvider
    from services.discussion_service import DiscussionService
    from services.llm_service import LLMService
    from services.observability import ObservabilityService
    from services.session_service import SessionService
    from services.turn_workflow import TurnWorkflowService
    from utils.execution_metrics import build_stream_execution_metrics, extract_execution_metrics
    from utils.pdf_export import export_session_pdf
    from utils.text_metrics import calculate_jaccard_entropy

# Initialize logging
_request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def _record_factory_with_request_id(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _previous_log_record_factory(*args, **kwargs)
    record.request_id = _request_id_context.get()
    return record


_previous_log_record_factory = logging.getLogRecordFactory()
logging.setLogRecordFactory(_record_factory_with_request_id)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [request_id=%(request_id)s] %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger("fontTools").setLevel(logging.WARNING)


async def _run_blocking_io(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run synchronous storage clients off the event loop while keeping call semantics unchanged."""
    return await asyncio.to_thread(partial(func, *args, **kwargs))


class AgentConfig(BaseModel):
    agent_id: str = Field(..., description="Unique agent identifier")
    display_name: str = Field(..., description="Human-readable agent name")
    system_prompt: str = Field(..., description="System prompt for the LLM")
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(default=512, ge=50, le=2048)


class ProcessTurnRequest(BaseModel):
    session_id: UUID = Field(..., description="Unique session identifier")
    topic: str = Field(..., min_length=1, max_length=255, description="Discussion topic")
    agent_id: str = Field(..., description="Agent to process turn for")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=1.5, description="Optional runtime temperature override from the UI")
    turn_number: Optional[int] = Field(default=None, ge=1, description="Turn number if already known")


class ProcessTurnResponse(BaseModel):
    message_id: UUID
    agent_id: str
    display_name: str
    message: str
    turn_number: int
    created_at: datetime
    telemetry: "TelemetryData"
    execution_metrics: "ExecutionMetrics"


class ProcessTurnStreamChunk(BaseModel):
    type: Literal["chunk"]
    content: str


class ProcessTurnStreamStatus(BaseModel):
    type: Literal["status"]
    stage: Literal["retrying"]
    message: str
    retry_after_seconds: float
    attempt_number: int


class ProcessTurnStreamFinal(BaseModel):
    type: Literal["final"]
    message_id: UUID
    agent_id: str
    display_name: str
    message: str
    turn_number: int
    created_at: datetime
    telemetry: "TelemetryData"
    execution_metrics: "ExecutionMetrics"


class GenerateRequest(BaseModel):
    session_id: UUID = Field(..., description="Unique session identifier")
    topic: str = Field(..., min_length=1, max_length=255, description="Discussion topic")
    agent_id: str = Field(..., description="Agent to generate response for")
    previous_response: Optional[str] = Field(None, description="Previous agent's response for entropy calculation")


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1)


class ChatStreamRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1, description="Conversation history from the frontend")
    agent_id: str = Field(..., description="Agent to respond as")
    session_id: Optional[UUID] = Field(default=None, description="Optional session identifier for persistence")
    topic: Optional[str] = Field(default=None, max_length=255, description="Optional topic label for persistence and prompt framing")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=1.5, description="Optional runtime temperature override")
    save_response: bool = Field(default=True, description="Persist the completed assistant response when a session id is provided")


class TelemetryData(BaseModel):
    entropy: float = Field(..., description="Jaccard Similarity Entropy Score (0.0-1.0)")
    latency_ms: int = Field(..., description="Response generation latency in milliseconds")
    word_count: int = Field(..., description="Total word count in generated response")
    vector: Optional["VectorTelemetry"] = Field(default=None, description="Speaker knowledge retrieval telemetry for this turn")


class VectorTelemetry(BaseModel):
    used: bool = Field(..., description="Whether speaker knowledge was injected into the prompt")
    match_count: int = Field(..., description="Number of retrieved knowledge chunks")
    top_score: Optional[float] = Field(None, description="Top retrieval similarity score")
    sources: List[str] = Field(default_factory=list, description="Unique source titles contributing context")
    chunk_ids: List[str] = Field(default_factory=list, description="Retrieved chunk ids for debugging")
    context_chars: int = Field(..., description="Total character count of injected knowledge text")


class ExecutionMetrics(BaseModel):
    generation_duration_ms: Optional[int] = Field(None, description="Provider-reported generation duration in milliseconds")
    prompt_tokens: Optional[int] = Field(None, description="Prompt tokens consumed")
    completion_tokens: Optional[int] = Field(None, description="Completion tokens generated")
    total_tokens: Optional[int] = Field(None, description="Total tokens consumed")
    tokens_per_second: Optional[float] = Field(None, description="Completion throughput in tokens per second")
    queue_time_ms: Optional[int] = Field(None, description="Provider-reported queue time in milliseconds, if available")
    prompt_time_ms: Optional[int] = Field(None, description="Provider-reported prompt processing time in milliseconds, if available")
    ttft_ms: Optional[int] = Field(None, description="Time to first token in milliseconds, if available")
    network_rtt_ms: Optional[int] = Field(None, description="Observed network round-trip for the inference request")
    provider: str = Field(default="llm", description="Current inference provider label")
    updated_at: datetime = Field(..., description="Timestamp of the latest execution metrics")


class GenerateResponse(BaseModel):
    response: str = Field(..., description="Generated response text")
    telemetry: TelemetryData = Field(..., description="Telemetry metrics")
    message_id: Optional[UUID] = Field(None, description="Message ID if persisted")
    turn_number: Optional[int] = Field(None, description="Turn number if persisted")


class ServiceStatus(BaseModel):
    name: str = Field(..., description="Display name of the service")
    status: str = Field(..., description="ONLINE or OFFLINE")
    latency_ms: Optional[int] = Field(None, description="Observed latency in milliseconds")
    detail: Optional[str] = Field(None, description="Optional diagnostic detail")


class SessionTopicUpdateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=255)


class AgentRegisterRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    system_prompt: str = Field(..., min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(default=512, ge=50, le=2048)


def _decode_redis_value(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _parse_agent_payload(agent_id: str, payload: str) -> AgentConfig:
    raw = json.loads(payload)
    return AgentConfig(
        agent_id=agent_id,
        display_name=raw["display_name"],
        system_prompt=raw["system_prompt"],
        temperature=float(raw.get("temperature", 0.7)),
        max_tokens=int(raw.get("max_tokens", 512)),
    )

redis: Redis
vector_index: Index
database_service: DatabaseService
agent_registry_service: AgentRegistryService
observability_service: ObservabilityService
session_service: SessionService
llm_service: LLMService
turn_workflow_service: TurnWorkflowService
discussion_service: DiscussionService


def _assign_runtime_globals(*, services: Dict[str, Any]) -> None:
    global redis, vector_index, database_service
    global agent_registry_service, observability_service, session_service
    global llm_service, turn_workflow_service, discussion_service

    redis = services["redis"]
    vector_index = services["vector_index"]
    database_service = services["database_service"]
    agent_registry_service = services["agent_registry_service"]
    observability_service = services["observability_service"]
    session_service = services["session_service"]
    llm_service = services["llm_service"]
    turn_workflow_service = services["turn_workflow_service"]
    discussion_service = services["discussion_service"]


def _build_services(settings: BackendSettings) -> Dict[str, Any]:
    return build_runtime_services(
        upstash_redis_rest_url=settings.storage.redis_rest_url,
        upstash_redis_rest_token=settings.storage.redis_rest_token,
        upstash_vector_rest_url=settings.storage.vector_rest_url,
        upstash_vector_rest_token=settings.storage.vector_rest_token,
        llm_api_base_url=settings.llm.api_base_url,
        llm_api_key=settings.llm.api_key,
        llm_model_id=settings.llm.model_id,
        llm_top_p=settings.llm.top_p,
        llm_429_max_retries=max(0, settings.llm.max_retries),
        llm_request_throttle_seconds=max(0.0, settings.llm.request_throttle_seconds),
        agent_registry_cache_ttl_seconds=settings.storage.agent_registry_cache_ttl_seconds,
        agent_config_cache_ttl_seconds=settings.storage.agent_config_cache_ttl_seconds,
        session_max_messages=settings.storage.session_max_messages,
        prompt_capture_backend=settings.storage.prompt_capture_backend,
        prompt_capture_max_entries=settings.storage.prompt_capture_max_entries,
        decode_redis_value=_decode_redis_value,
        parse_agent_payload=_parse_agent_payload,
        run_blocking_io=_run_blocking_io,
        calculate_entropy=calculate_jaccard_entropy,
        execution_metrics_model=ExecutionMetrics,
        extract_execution_metrics=extract_execution_metrics,
        build_stream_execution_metrics=build_stream_execution_metrics,
        telemetry_model=TelemetryData,
        vector_telemetry_model=VectorTelemetry,
        process_turn_response_model=ProcessTurnResponse,
        process_turn_stream_chunk_model=ProcessTurnStreamChunk,
        process_turn_stream_status_model=ProcessTurnStreamStatus,
        process_turn_stream_final_model=ProcessTurnStreamFinal,
        generate_response_model=GenerateResponse,
        streaming_response_factory=StreamingResponse,
        export_session_pdf=export_session_pdf,
        prompt_capture_log_path=settings.base_dir / "backend" / "logs" / "provider_prompt_captures.jsonl",
        logger=logger,
    )


def _build_lifespan(
    *,
    llm_service: LLMService,
    observability_service: ObservabilityService,
    startup_readiness_mode: Literal["off", "warn", "strict"],
):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        shared_http_client = httpx.AsyncClient(timeout=httpx.Timeout(90.0, read=90.0))
        llm_service.set_shared_http_client(shared_http_client)
        observability_service.set_shared_http_client(shared_http_client)
        app.state.shared_http_client = shared_http_client
        try:
            if startup_readiness_mode != "off":
                readiness = await observability_service.check_services()
                app.state.startup_readiness = readiness
                offline_services = [
                    service for service in readiness.get("services", []) if service.get("status") != "ONLINE"
                ]
                if offline_services:
                    offline_summary = ", ".join(
                        f"{service.get('name', 'unknown')}: {service.get('detail') or service.get('status', 'OFFLINE')}"
                        for service in offline_services
                    )
                    message = f"Startup readiness failed: {offline_summary}"
                    if startup_readiness_mode == "warn":
                        logger.warning(message)
                    else:
                        logger.error(message)
                        raise RuntimeError(message)
                else:
                    logger.info("Startup readiness passed")
            else:
                app.state.startup_readiness = {
                    "status": "SKIPPED",
                    "services": [],
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
            yield
        finally:
            llm_service.set_shared_http_client(None)
            observability_service.set_shared_http_client(None)
            app.state.shared_http_client = None
            await shared_http_client.aclose()

    return lifespan


def create_app(settings: Optional[BackendSettings] = None) -> FastAPI:
    active_settings = settings or load_settings()
    services = _build_services(active_settings)
    _assign_runtime_globals(services=services)

    app = FastAPI(
        title="EXHUMED",
        version="1.1.0",
        description="Decoupled AI discussion platform with Upstash Redis + Vector",
        lifespan=_build_lifespan(
            llm_service=services["llm_service"],
            observability_service=services["observability_service"],
            startup_readiness_mode=active_settings.runtime.startup_readiness_mode,
        ),
    )
    app.state.services = services
    app.state.settings = active_settings

    # ------------------------------------------------------------------
    # Health / readiness endpoints — registered before auth middleware so
    # Railway's health checks and load-balancer probes never need a key.
    # ------------------------------------------------------------------

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        """Liveness probe — always returns 200 while the process is alive."""
        return {"status": "alive"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz():
        """Readiness probe — reflects the result of the startup dependency check."""
        readiness = getattr(app.state, "startup_readiness", None)
        if readiness is None:
            return JSONResponse(status_code=503, content={"status": "initializing"})
        overall = readiness.get("status", "UNKNOWN")
        http_status = 200 if overall in ("OPTIMAL", "SKIPPED") else 503
        return JSONResponse(status_code=http_status, content=readiness)

    # ------------------------------------------------------------------
    # Optional API-key authentication middleware
    # ------------------------------------------------------------------

    _auth_api_key = active_settings.auth.api_key

    if _auth_api_key:
        # Paths that bypass auth entirely (health probes + CORS preflight).
        _UNPROTECTED_PATHS = {"/healthz", "/readyz"}

        @app.middleware("http")
        async def enforce_api_key(request, call_next):
            if request.method == "OPTIONS" or request.url.path in _UNPROTECTED_PATHS:
                return await call_next(request)

            # Accept either X-API-Key header or Authorization: Bearer <key>
            provided_key = request.headers.get("X-API-Key", "").strip()
            if not provided_key:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.lower().startswith("bearer "):
                    provided_key = auth_header[7:].strip()

            if provided_key != _auth_api_key:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Unauthorized"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return await call_next(request)

    @app.middleware("http")
    async def attach_request_context(request, call_next):
        request_id = request.headers.get("X-Request-ID", "").strip() or str(uuid4())
        request.state.request_id = request_id
        context_token = _request_id_context.set(request_id)
        started_at = datetime.now(timezone.utc)
        logger.info("Request started: method=%s path=%s", request.method, request.url.path)

        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Request failed: method=%s path=%s", request.method, request.url.path)
            raise
        finally:
            _request_id_context.reset(context_token)

        # For streaming responses (StreamingResponse / SSE) call_next() returns
        # as soon as the response *headers* are sent — the body is still being
        # produced asynchronously.  Labelling that elapsed time "duration_ms"
        # is misleading in monitoring tools, so we distinguish the two cases.
        elapsed_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
        response.headers["X-Request-ID"] = request_id

        is_streaming = response.headers.get("content-type", "").startswith("text/") and \
            response.headers.get("transfer-encoding", "") == "chunked" or \
            "stream" in response.headers.get("content-type", "")

        completion_token = _request_id_context.set(request_id)
        try:
            if is_streaming:
                logger.info(
                    "Stream response headers sent: method=%s path=%s status=%s ttfb_ms=%s",
                    request.method,
                    request.url.path,
                    response.status_code,
                    elapsed_ms,
                )
            else:
                logger.info(
                    "Request completed: method=%s path=%s status=%s duration_ms=%s",
                    request.method,
                    request.url.path,
                    response.status_code,
                    elapsed_ms,
                )
        finally:
            _request_id_context.reset(completion_token)
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors.allow_origins,
        allow_origin_regex=active_settings.cors.allow_origin_regex,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    if active_settings.static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(active_settings.static_dir)), name="static")
    else:
        logger.warning("Static directory not found at %s; /static route disabled", active_settings.static_dir)

    app.include_router(create_root_router())
    app.include_router(create_telemetry_router(observability_service=services["observability_service"]))
    app.include_router(
        create_session_router(
            session_service=services["session_service"],
            logger=logger,
            session_topic_update_request_model=SessionTopicUpdateRequest,
        )
    )
    app.include_router(
        create_agent_router(
            agent_registry_service=services["agent_registry_service"],
            logger=logger,
            agent_register_request_model=AgentRegisterRequest,
        )
    )
    app.include_router(
        create_discussion_router(
            discussion_service=services["discussion_service"],
            process_turn_request_model=ProcessTurnRequest,
            process_turn_response_model=ProcessTurnResponse,
            generate_request_model=GenerateRequest,
            generate_response_model=GenerateResponse,
            chat_stream_request_model=ChatStreamRequest,
        )
    )
    app.include_router(create_export_router(session_service=services["session_service"], logger=logger))
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    return app

async def http_exception_handler(request, exc):
    logger.error("HTTP Exception: %s", exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


async def request_validation_exception_handler(request, exc: RequestValidationError):
    logger.warning(
        "Request validation failed: method=%s path=%s errors=%s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
