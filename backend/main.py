"""
EXHUMED: FastAPI Backend
Decoupled AI discussion platform with dynamic agent registry.

Storage stack:
- Upstash Redis: agent registry and ordered session message index
- Upstash Vector: discussion message vectors for semantic retrieval
"""

import asyncio
from functools import partial
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from upstash_redis import Redis
from upstash_vector import Index

try:
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

redis = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)
vector_index = Index(url=UPSTASH_VECTOR_REST_URL, token=UPSTASH_VECTOR_REST_TOKEN)
database_service = DatabaseService(
    redis_client=redis,
    vector_index=vector_index,
    embedding_provider=SentenceTransformerEmbeddingProvider(),
)

app = FastAPI(
    title="EXHUMED",
    version="1.1.0",
    description="Decoupled AI discussion platform with Upstash Redis + Vector",
)
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


agent_registry_service = AgentRegistryService(
    redis_client=redis,
    decode_value=_decode_redis_value,
    parse_agent_payload=_parse_agent_payload,
    run_blocking_io=_run_blocking_io,
    registry_ttl_seconds=AGENT_REGISTRY_CACHE_TTL_SECONDS,
    config_ttl_seconds=AGENT_CONFIG_CACHE_TTL_SECONDS,
)

observability_service = ObservabilityService(
    redis_client=redis,
    vector_index=vector_index,
    decode_value=_decode_redis_value,
    run_blocking_io=_run_blocking_io,
    execution_metrics_model=ExecutionMetrics,
    llm_api_base_url=LLM_API_BASE_URL,
    llm_api_key=LLM_API_KEY,
    logger=logger,
)

session_service = SessionService(
    redis_client=redis,
    database_service=database_service,
    run_blocking_io=_run_blocking_io,
    decode_value=_decode_redis_value,
    export_session_pdf=export_session_pdf,
    logger=logger,
)

llm_service = LLMService(
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


turn_workflow_service = TurnWorkflowService(
    fetch_agent_config=agent_registry_service.fetch_agent_config,
    fetch_context_messages=session_service.fetch_context_messages,
    get_agent_context_matches=session_service.get_agent_context_matches,
    sanitize_generated_message=session_service.sanitize_generated_message,
    save_latest_execution_metrics=observability_service.save_latest_execution_metrics_async,
    persist_session_telemetry=session_service.persist_session_telemetry_async,
    save_message_to_storage=session_service.save_message_to_storage,
    calculate_entropy=calculate_jaccard_entropy,
    build_telemetry=TelemetryData,
)

discussion_service = DiscussionService(
    turn_workflow_service=turn_workflow_service,
    session_service=session_service,
    llm_service=llm_service,
    fetch_agent_config=agent_registry_service.fetch_agent_config,
    save_latest_execution_metrics=observability_service.save_latest_execution_metrics_async,
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


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "name": "EXHUMED",
        "version": "1.1.0",
        "status": "operational",
        "storage": "upstash-redis-vector",
        "endpoints": {
            "process_turn": "/process-turn (POST)",
            "generate_with_telemetry": "/generate (POST) - includes Jaccard Entropy telemetry",
            "chat_stream": "/chat/stream (POST) - plain text streaming for the Next.js frontend",
            "export_pdf": "/export-pdf/{session_id} (GET)",
            "list_agents": "/agents (GET)",
            "register_agent": "/agents/register (POST)",
            "get_session_topic": "/sessions/{session_id}/topic (GET)",
            "set_session_topic": "/sessions/{session_id}/topic (POST)",
        },
    }


@app.get("/services-status")
async def services_status() -> Dict[str, Any]:
    return await observability_service.check_services()


@app.get("/telemetry/latest")
async def latest_telemetry() -> Dict[str, Any]:
    metrics = observability_service.fetch_latest_execution_metrics()
    if metrics is None:
        return {"status": "idle", "metrics": None}
    return {"status": "ok", "metrics": metrics.model_dump(mode="json")}


@app.get("/sessions/{session_id}/topic")
async def get_session_topic(session_id: UUID) -> Dict[str, Any]:
    topic = await session_service.fetch_session_topic(session_id)
    return {"session_id": str(session_id), "topic": topic}


@app.post("/sessions/{session_id}/topic")
async def set_session_topic(session_id: UUID, request: SessionTopicUpdateRequest) -> Dict[str, Any]:
    await session_service.save_session_topic(session_id, request.topic)
    return {"status": "ok", "session_id": str(session_id), "topic": request.topic}


@app.delete("/sessions/{session_id}")
async def clear_session(session_id: UUID) -> Dict[str, Any]:
    try:
        await session_service.clear_session_storage(session_id)
        return {"status": "ok", "session_id": str(session_id)}
    except Exception as exc:
        logger.error("Error clearing session %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail="Error clearing session")


@app.post("/agents/register")
async def register_agent(request: AgentRegisterRequest) -> Dict[str, Any]:
    payload = {
        "display_name": request.display_name,
        "system_prompt": request.system_prompt,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
    }

    try:
        await agent_registry_service.register_agent(request.agent_id, payload)
        return {"status": "ok", "agent_id": request.agent_id}
    except Exception as exc:
        logger.error("Error registering agent %s: %s", request.agent_id, exc)
        raise HTTPException(status_code=500, detail="Error registering agent")


@app.get("/agents")
async def list_agents() -> Dict[str, Any]:
    try:
        agents = await agent_registry_service.list_agents()
        return {"agents": agents}
    except Exception as exc:
        logger.error("Error listing agents: %s", exc)
        raise HTTPException(status_code=500, detail="Error retrieving agents")


@app.post("/process-turn", response_model=ProcessTurnResponse)
async def process_turn(request: ProcessTurnRequest) -> ProcessTurnResponse:
    return await discussion_service.process_turn(request)


@app.post("/process-turn/stream")
async def process_turn_stream(request: ProcessTurnRequest) -> StreamingResponse:
    return await discussion_service.process_turn_stream(request)


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    return await discussion_service.generate(request)


@app.post("/chat/stream")
async def chat_stream(request: ChatStreamRequest) -> StreamingResponse:
    return await discussion_service.chat_stream(request)


@app.get("/export-pdf/{session_id}")
async def export_pdf(session_id: UUID) -> FileResponse:
    logger.info("Exporting PDF for session: %s", session_id)

    try:
        pdf_path = await session_service.export_pdf_file(session_id)

        return FileResponse(
            path=pdf_path,
            filename=f"exhumed_discussion_{session_id}.pdf",
            media_type="application/pdf",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error generating PDF for %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail="Error generating PDF export")


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logger.error("HTTP Exception: %s", exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
