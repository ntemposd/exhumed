"""
EXHUMED: FastAPI Backend
Decoupled AI discussion platform with dynamic agent registry.

Storage stack:
- Upstash Redis: agent registry and ordered session message index
- Upstash Vector: discussion message vectors for semantic retrieval
"""

import asyncio
from contextlib import asynccontextmanager
from functools import partial
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional
from uuid import UUID

from dotenv import load_dotenv
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from upstash_redis import Redis
from upstash_vector import Index

try:
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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

AGENT_REGISTRY_CACHE_TTL_SECONDS = 60.0
AGENT_CONFIG_CACHE_TTL_SECONDS = 300.0

FILE_DIR = Path(__file__).resolve().parent
REPO_ROOT_CANDIDATE = FILE_DIR.parent

# Support two deployment layouts:
# 1) repo-root deploy: /app/backend/main.py
# 2) backend-only deploy: /app/main.py
if (REPO_ROOT_CANDIDATE / "backend" / "main.py").exists():
    BASE_DIR = REPO_ROOT_CANDIDATE
else:
    BASE_DIR = FILE_DIR

STATIC_DIR = BASE_DIR / "static"

# Load environment variables from the local .env file when present.
load_dotenv(BASE_DIR / ".env")

# Upstash and model config
UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")
UPSTASH_VECTOR_REST_URL = os.getenv("UPSTASH_VECTOR_REST_URL")
UPSTASH_VECTOR_REST_TOKEN = os.getenv("UPSTASH_VECTOR_REST_TOKEN")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "llama-3.1-8b-instant")
LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL", "https://api.groq.com/openai/v1")
LLM_429_MAX_RETRIES = max(0, int(os.getenv("LLM_429_MAX_RETRIES", "3")))
LLM_REQUEST_THROTTLE_SECONDS = max(0.0, float(os.getenv("LLM_REQUEST_THROTTLE_SECONDS", "0.0")))


def _parse_cors_origins(raw_value: Optional[str]) -> List[str]:
    if not raw_value:
        return []
    return [origin.strip().rstrip("/") for origin in raw_value.split(",") if origin.strip()]


async def _run_blocking_io(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run synchronous storage clients off the event loop while keeping call semantics unchanged."""
    return await asyncio.to_thread(partial(func, *args, **kwargs))


DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]
CORS_ALLOW_ORIGINS = _parse_cors_origins(os.getenv("CORS_ALLOW_ORIGINS")) or DEFAULT_CORS_ORIGINS
CORS_ALLOW_ORIGIN_REGEX = os.getenv(
    "CORS_ALLOW_ORIGIN_REGEX",
    r"https://.*\.vercel\.app|https?://(?:localhost|127\.0\.0\.1)(?::\d+)?",
)

missing_env: List[str] = []
for env_name in (
    "UPSTASH_REDIS_REST_URL",
    "UPSTASH_REDIS_REST_TOKEN",
    "UPSTASH_VECTOR_REST_URL",
    "UPSTASH_VECTOR_REST_TOKEN",
):
    if not os.getenv(env_name):
        missing_env.append(env_name)

if not LLM_API_KEY:
    missing_env.append("LLM_API_KEY")

if missing_env:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_env)}")


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


def _build_services() -> Dict[str, Any]:
    redis_client = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)
    vector_client = Index(url=UPSTASH_VECTOR_REST_URL, token=UPSTASH_VECTOR_REST_TOKEN)
    database = DatabaseService(
        redis_client=redis_client,
        vector_index=vector_client,
        embedding_provider=SentenceTransformerEmbeddingProvider(),
    )
    agent_registry = AgentRegistryService(
        redis_client=redis_client,
        decode_value=_decode_redis_value,
        parse_agent_payload=_parse_agent_payload,
        run_blocking_io=_run_blocking_io,
        registry_ttl_seconds=AGENT_REGISTRY_CACHE_TTL_SECONDS,
        config_ttl_seconds=AGENT_CONFIG_CACHE_TTL_SECONDS,
    )
    observability = ObservabilityService(
        redis_client=redis_client,
        vector_index=vector_client,
        decode_value=_decode_redis_value,
        run_blocking_io=_run_blocking_io,
        execution_metrics_model=ExecutionMetrics,
        llm_api_base_url=LLM_API_BASE_URL,
        llm_api_key=LLM_API_KEY,
        logger=logger,
    )
    session = SessionService(
        redis_client=redis_client,
        database_service=database,
        run_blocking_io=_run_blocking_io,
        decode_value=_decode_redis_value,
        export_session_pdf=export_session_pdf,
        logger=logger,
    )
    llm = LLMService(
        api_base_url=LLM_API_BASE_URL,
        api_key=LLM_API_KEY,
        model_id=LLM_MODEL_ID,
        max_retries=LLM_429_MAX_RETRIES,
        throttle_seconds=LLM_REQUEST_THROTTLE_SECONDS,
        execution_metrics_builder=ExecutionMetrics,
        extract_execution_metrics=extract_execution_metrics,
        build_stream_execution_metrics=build_stream_execution_metrics,
        logger=logger,
    )
    turn_workflow = TurnWorkflowService(
        fetch_agent_config=agent_registry.fetch_agent_config,
        fetch_context_messages=session.fetch_context_messages,
        get_agent_context_matches=session.get_agent_context_matches,
        sanitize_generated_message=session.sanitize_generated_message,
        save_latest_execution_metrics=observability.save_latest_execution_metrics_async,
        persist_session_telemetry=session.persist_session_telemetry_async,
        save_message_to_storage=session.save_message_to_storage,
        calculate_entropy=calculate_jaccard_entropy,
        build_telemetry=TelemetryData,
    )
    discussion = DiscussionService(
        turn_workflow_service=turn_workflow,
        session_service=session,
        llm_service=llm,
        fetch_agent_config=agent_registry.fetch_agent_config,
        save_latest_execution_metrics=observability.save_latest_execution_metrics_async,
        process_turn_response_model=ProcessTurnResponse,
        process_turn_stream_chunk_model=ProcessTurnStreamChunk,
        process_turn_stream_status_model=ProcessTurnStreamStatus,
        process_turn_stream_final_model=ProcessTurnStreamFinal,
        generate_response_model=GenerateResponse,
        streaming_response_factory=StreamingResponse,
        vector_telemetry_model=VectorTelemetry,
        logger=logger,
        utcnow=lambda: datetime.now(timezone.utc),
    )
    return {
        "redis": redis_client,
        "vector_index": vector_client,
        "database_service": database,
        "agent_registry_service": agent_registry,
        "observability_service": observability,
        "session_service": session,
        "llm_service": llm,
        "turn_workflow_service": turn_workflow,
        "discussion_service": discussion,
    }


def _build_lifespan(*, llm_service: LLMService, observability_service: ObservabilityService):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        shared_http_client = httpx.AsyncClient(timeout=httpx.Timeout(90.0, read=90.0))
        llm_service.set_shared_http_client(shared_http_client)
        observability_service.set_shared_http_client(shared_http_client)
        app.state.shared_http_client = shared_http_client
        try:
            yield
        finally:
            llm_service.set_shared_http_client(None)
            observability_service.set_shared_http_client(None)
            app.state.shared_http_client = None
            await shared_http_client.aclose()

    return lifespan


def create_app() -> FastAPI:
    services = _build_services()
    _assign_runtime_globals(services=services)

    app = FastAPI(
        title="EXHUMED",
        version="1.1.0",
        description="Decoupled AI discussion platform with Upstash Redis + Vector",
        lifespan=_build_lifespan(
            llm_service=services["llm_service"],
            observability_service=services["observability_service"],
        ),
    )
    app.state.services = services
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_origin_regex=CORS_ALLOW_ORIGIN_REGEX,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    else:
        logger.warning("Static directory not found at %s; /static route disabled", STATIC_DIR)

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
    return app

async def http_exception_handler(request, exc):
    logger.error("HTTP Exception: %s", exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
