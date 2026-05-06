"""
EXHUMED: FastAPI Backend
Decoupled AI discussion platform with dynamic agent registry.

Storage stack:
- Upstash Redis: agent registry and ordered session message index
- Upstash Vector: discussion message vectors for semantic retrieval
"""

import asyncio
import contextlib
import json
import logging
import os
import re
import string
import tempfile
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Literal, Optional, Tuple
from uuid import UUID, uuid4

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fpdf import FPDF
from pydantic import BaseModel, Field
from upstash_redis import Redis
from upstash_vector import Index

from backend.services.database import DatabaseService, SentenceTransformerEmbeddingProvider

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

AGENT_REGISTRY_CACHE_TTL_SECONDS = 60.0
AGENT_CONFIG_CACHE_TTL_SECONDS = 300.0
VECTOR_CAPABILITIES_CACHE_TTL_SECONDS = 300.0
_agent_registry_cache: Dict[str, Any] = {
    "expires_at": 0.0,
    "agents": [],
}
_agent_config_cache: Dict[str, Dict[str, Any]] = {}
_vector_capabilities_cache: Dict[str, Any] = {
    "expires_at": 0.0,
    "supports_text_upsert": None,
    "detail": None,
}
_vector_write_status: Dict[str, Any] = {
    "status": "unknown",
    "detail": None,
    "updated_at": None,
}

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

PDF_FONT_SEARCH_PATHS = {
    "regular": [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    ],
    "bold": [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeuib.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arialbd.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
    ],
    "italic": [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeuii.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "ariali.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Italic.ttf"),
    ],
}

PDF_TEXT_REPLACEMENTS = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\u00a0": " ",
    }
)

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

_llm_provider_gate_lock = asyncio.Lock()
_llm_provider_last_request_at = 0.0
_llm_provider_cooldown_until = 0.0


def _parse_cors_origins(raw_value: Optional[str]) -> List[str]:
    if not raw_value:
        return []
    return [origin.strip().rstrip("/") for origin in raw_value.split(",") if origin.strip()]


def _extract_provider_error_text(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            error_payload = data.get("error")
            if isinstance(error_payload, dict):
                return str(
                    error_payload.get("message")
                    or error_payload.get("error")
                    or error_payload.get("code")
                    or error_payload
                )
            return str(data.get("message") or data.get("error") or data)
        return str(data)
    except Exception:
        if response is None:
            return "No response body"

        try:
            return response.text[:300]
        except Exception:
            return f"HTTP {response.status_code} with unread or unavailable response body"


def _read_mapping_or_attr(value: Any, *names: str) -> Any:
    if isinstance(value, dict):
        for name in names:
            if name in value and value[name] is not None:
                return value[name]

    for name in names:
        candidate = getattr(value, name, None)
        if candidate is not None:
            return candidate

    return None


def _inspect_vector_text_upsert_support(info: Any) -> Tuple[bool, str]:
    dense_index = _read_mapping_or_attr(info, "dense_index", "denseIndex", "dense")
    sparse_index = _read_mapping_or_attr(info, "sparse_index", "sparseIndex", "sparse")
    embedding_models: List[str] = []

    for index_details in (dense_index, sparse_index):
        embedding_model = _read_mapping_or_attr(index_details, "embedding_model", "embeddingModel")
        if embedding_model:
            embedding_models.append(str(embedding_model))

    if embedding_models:
        return True, f"Embedding model configured: {', '.join(embedding_models)}"

    return False, "Index has no hosted embedding model; raw text upserts require an embedding-enabled Upstash Vector index."


def _vector_index_supports_text_upsert(*, force_refresh: bool = False) -> Tuple[bool, str]:
    now = time.monotonic()
    cached_support = _vector_capabilities_cache.get("supports_text_upsert")
    cached_detail = str(_vector_capabilities_cache.get("detail") or "")

    if (
        not force_refresh
        and cached_support is not None
        and now < float(_vector_capabilities_cache.get("expires_at") or 0.0)
    ):
        return bool(cached_support), cached_detail

    info = vector_index.info()
    supports_text_upsert, detail = _inspect_vector_text_upsert_support(info)
    _vector_capabilities_cache.update(
        {
            "expires_at": now + VECTOR_CAPABILITIES_CACHE_TTL_SECONDS,
            "supports_text_upsert": supports_text_upsert,
            "detail": detail,
        }
    )
    return supports_text_upsert, detail


def _record_vector_write_status(success: bool, detail: Optional[str] = None) -> None:
    _vector_write_status.update(
        {
            "status": "ok" if success else "error",
            "detail": (detail or "")[:240] if detail else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _parse_retry_after_seconds(response: httpx.Response, error_text: str) -> float:
    retry_after_value = response.headers.get("retry-after") if response is not None else None
    if retry_after_value:
        try:
            return max(0.0, float(retry_after_value.strip()))
        except ValueError:
            pass

    retry_match = re.search(r"try again in\s*([0-9]+(?:\.[0-9]+)?)s", error_text, flags=re.IGNORECASE)
    if retry_match:
        return max(0.0, float(retry_match.group(1)))

    return 0.0


async def _wait_for_provider_slot() -> None:
    global _llm_provider_last_request_at

    async with _llm_provider_gate_lock:
        now = time.monotonic()
        earliest_request_time = max(
            _llm_provider_cooldown_until,
            _llm_provider_last_request_at + LLM_REQUEST_THROTTLE_SECONDS,
        )
        sleep_for = earliest_request_time - now

        if sleep_for > 0:
            logger.info("Throttling LLM provider requests for %.2fs", sleep_for)
            await asyncio.sleep(sleep_for)

        _llm_provider_last_request_at = time.monotonic()


async def _register_provider_cooldown(delay_seconds: float) -> float:
    global _llm_provider_cooldown_until

    bounded_delay = max(0.0, delay_seconds)
    if bounded_delay <= 0:
        return 0.0

    async with _llm_provider_gate_lock:
        _llm_provider_cooldown_until = max(_llm_provider_cooldown_until, time.monotonic() + bounded_delay)

    return bounded_delay


async def _sleep_for_retry(delay_seconds: float, attempt_number: int) -> None:
    retry_delay = await _register_provider_cooldown(delay_seconds)
    logger.warning(
        "LLM provider returned 429, backing off for %.2fs before retry %s/%s",
        retry_delay,
        attempt_number,
        LLM_429_MAX_RETRIES,
    )
    await asyncio.sleep(retry_delay)


DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
CORS_ALLOW_ORIGINS = _parse_cors_origins(os.getenv("CORS_ALLOW_ORIGINS")) or DEFAULT_CORS_ORIGINS
CORS_ALLOW_ORIGIN_REGEX = os.getenv("CORS_ALLOW_ORIGIN_REGEX", r"https://.*\.vercel\.app")

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


def _clean_text(text: str) -> str:
    """Clean text for Jaccard Similarity: lowercase, remove punctuation, tokenize into words."""
    # Lowercase and remove punctuation
    text = text.lower()
    text = re.sub(f"[{re.escape(string.punctuation)}]", " ", text)
    # Tokenize into set of unique words (no duplicates, no empty strings)
    words = set(word for word in text.split() if word.strip())
    return words


def calculate_jaccard_entropy(text1: str, text2: str) -> float:
    """
    Calculate Jaccard Similarity Entropy Index.
    
    Formula:
    - Jaccard Similarity = |Intersection| / |Union|
    - Entropy Score = 1 - Similarity (where 1 = maximum divergence, 0 = identical)
    
    Args:
        text1: First text (usually current response)
        text2: Second text (usually previous response)
    
    Returns:
        float: Entropy score in range [0.0, 1.0]
        - 0.0: Texts are identical (no entropy)
        - 1.0: Texts are completely different (maximum entropy)
    """
    if not text1 or not text2:
        # If either text is empty, return default entropy
        return 0.0 if (not text1 and not text2) else 1.0
    
    # Clean and convert to sets
    words_text1 = _clean_text(text1)
    words_text2 = _clean_text(text2)
    
    if not words_text1 or not words_text2:
        # If either set is empty after cleaning
        return 1.0 if (words_text1 != words_text2) else 0.0
    
    # Calculate Jaccard Similarity using set operations (optimized)
    intersection = len(words_text1 & words_text2)  # Set intersection
    union = len(words_text1 | words_text2)  # Set union
    
    if union == 0:
        jaccard_similarity = 0.0
    else:
        jaccard_similarity = intersection / union
    
    # Convert similarity to entropy: 1 - similarity
    entropy = 1.0 - jaccard_similarity
    
    return round(entropy, 4)


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


def invalidate_agent_registry_cache() -> None:
    _agent_registry_cache["expires_at"] = 0.0
    _agent_registry_cache["agents"] = []


def invalidate_agent_config_cache(agent_id: Optional[str] = None) -> None:
    if agent_id is None:
        _agent_config_cache.clear()
        return
    _agent_config_cache.pop(agent_id, None)


def get_cached_agent_registry() -> Optional[List[Dict[str, Any]]]:
    if time.monotonic() >= float(_agent_registry_cache["expires_at"]):
        return None
    cached_agents = _agent_registry_cache.get("agents", [])
    return [dict(agent) for agent in cached_agents]


def set_cached_agent_registry(agents: List[Dict[str, Any]]) -> None:
    _agent_registry_cache["agents"] = [dict(agent) for agent in agents]
    _agent_registry_cache["expires_at"] = time.monotonic() + AGENT_REGISTRY_CACHE_TTL_SECONDS


def get_cached_agent_config(agent_id: str) -> Optional[AgentConfig]:
    cached_item = _agent_config_cache.get(agent_id)
    if not cached_item:
        return None
    if time.monotonic() >= float(cached_item["expires_at"]):
        _agent_config_cache.pop(agent_id, None)
        return None
    cached_config = cached_item["agent_config"]
    if isinstance(cached_config, AgentConfig):
        return cached_config.model_copy(deep=True)
    return None


def set_cached_agent_config(agent_config: AgentConfig) -> None:
    _agent_config_cache[agent_config.agent_id] = {
        "expires_at": time.monotonic() + AGENT_CONFIG_CACHE_TTL_SECONDS,
        "agent_config": agent_config.model_copy(deep=True),
    }


def _load_message_record(raw_entry: Any) -> Optional[Dict[str, Any]]:
    decoded_entry = _decode_redis_value(raw_entry)

    try:
        item = json.loads(decoded_entry)
        if isinstance(item, dict) and "message" in item:
            return item
    except json.JSONDecodeError:
        pass

    try:
        payload = redis.get(f"message:{decoded_entry}")
        if not payload:
            return None
        item = json.loads(_decode_redis_value(payload))
        return item if isinstance(item, dict) else None
    except Exception:
        return None


def _extract_legacy_message_key(raw_entry: Any) -> Optional[str]:
    decoded_entry = _decode_redis_value(raw_entry)

    try:
        item = json.loads(decoded_entry)
        if isinstance(item, dict) and "message" in item:
            return None
    except json.JSONDecodeError:
        pass

    return f"message:{decoded_entry}" if decoded_entry else None


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_ttft_ms(headers: httpx.Headers) -> Optional[int]:
    candidate_keys = (
        "x-ttft-ms",
        "x-ttft",
        "ttft-ms",
        "openai-processing-ms",
        "x-openai-processing-ms",
    )
    for key in candidate_keys:
        value = headers.get(key)
        parsed = _safe_int(value)
        if parsed is not None:
            return parsed
    return None


def _estimate_ttft_ms(
    headers: httpx.Headers,
    queue_time_ms: Optional[int],
    prompt_time_ms: Optional[int],
) -> Optional[int]:
    provider_ttft_ms = _extract_ttft_ms(headers)
    if provider_ttft_ms is not None:
        return provider_ttft_ms

    timing_parts = [value for value in (queue_time_ms, prompt_time_ms) if isinstance(value, int)]
    if timing_parts:
        return sum(timing_parts)

    return None


def _extract_execution_metrics(
    data: Dict[str, Any],
    headers: httpx.Headers,
    network_rtt_ms: int,
) -> ExecutionMetrics:
    usage = data.get("usage") if isinstance(data, dict) else {}
    usage = usage if isinstance(usage, dict) else {}

    prompt_tokens = _safe_int(usage.get("prompt_tokens"))
    completion_tokens = _safe_int(usage.get("completion_tokens"))
    total_tokens = _safe_int(usage.get("total_tokens"))
    queue_time_s = _safe_float(usage.get("queue_time"))
    prompt_time_s = _safe_float(usage.get("prompt_time"))

    generation_duration_s = (
        _safe_float(usage.get("total_time"))
        or _safe_float(usage.get("completion_time"))
    )
    queue_time_ms = int(queue_time_s * 1000) if queue_time_s is not None else None
    prompt_time_ms = int(prompt_time_s * 1000) if prompt_time_s is not None else None
    ttft_ms = _estimate_ttft_ms(headers, queue_time_ms, prompt_time_ms)
    generation_duration_ms = (
        int(generation_duration_s * 1000) if generation_duration_s is not None else None
    )

    tokens_per_second: Optional[float] = None
    if completion_tokens and generation_duration_s and generation_duration_s > 0:
        tokens_per_second = round(completion_tokens / generation_duration_s, 2)

    return ExecutionMetrics(
        generation_duration_ms=generation_duration_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        tokens_per_second=tokens_per_second,
        queue_time_ms=queue_time_ms,
        prompt_time_ms=prompt_time_ms,
        ttft_ms=ttft_ms,
        network_rtt_ms=network_rtt_ms,
        provider="llm",
        updated_at=datetime.now(timezone.utc),
    )


def save_latest_execution_metrics(metrics: ExecutionMetrics) -> None:
    try:
        redis.set("telemetry:latest", metrics.model_dump_json())
    except Exception as exc:
        logger.warning("Unable to persist latest execution telemetry: %s", exc)


def fetch_latest_execution_metrics() -> Optional[ExecutionMetrics]:
    try:
        payload = redis.get("telemetry:latest")
        if not payload:
            return None
        raw = json.loads(_decode_redis_value(payload))
        if isinstance(raw, dict):
            return ExecutionMetrics.model_validate(raw)
    except Exception as exc:
        logger.warning("Unable to load latest execution telemetry: %s", exc)
    return None


async def check_services() -> Dict[str, Any]:
    services: List[ServiceStatus] = []

    redis_started = time.perf_counter()
    try:
        redis.ping()
        redis_latency_ms = int((time.perf_counter() - redis_started) * 1000)
        services.append(
            ServiceStatus(
                name="Redis",
                status="ONLINE",
                latency_ms=redis_latency_ms,
            )
        )
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        services.append(
            ServiceStatus(
                name="Redis",
                status="OFFLINE",
                detail=str(exc)[:160],
            )
        )

    vector_started = time.perf_counter()
    try:
        vector_index.info()
        vector_latency_ms = int((time.perf_counter() - vector_started) * 1000)
        services.append(
            ServiceStatus(
                name="Vector",
                status="ONLINE",
                latency_ms=vector_latency_ms,
            )
        )
    except Exception as exc:
        logger.warning("Upstash Vector health check failed: %s", exc)
        services.append(
            ServiceStatus(
                name="Vector",
                status="OFFLINE",
                detail=str(exc)[:160],
            )
        )

    inference_started = time.perf_counter()
    try:
        headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{LLM_API_BASE_URL}/models", headers=headers)
            response.raise_for_status()
        inference_latency_ms = int((time.perf_counter() - inference_started) * 1000)
        services.append(
            ServiceStatus(
                name="Inference",
                status="ONLINE",
                latency_ms=inference_latency_ms,
            )
        )
    except Exception as exc:
        logger.warning("Inference health check failed: %s", exc)
        services.append(
            ServiceStatus(
                name="Inference",
                status="OFFLINE",
                detail=str(exc)[:160],
            )
        )

    overall_status = (
        "OPTIMAL" if all(service.status == "ONLINE" for service in services) else "DEGRADED"
    )
    return {
        "status": overall_status,
        "services": [service.model_dump() for service in services],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def fetch_agent_config(agent_id: str) -> AgentConfig:
    try:
        cached_config = get_cached_agent_config(agent_id)
        if cached_config is not None:
            return cached_config

        payload = redis.get(f"agent:{agent_id}")
        if not payload:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found in registry")
        agent_config = _parse_agent_payload(agent_id, _decode_redis_value(payload))
        set_cached_agent_config(agent_config)
        return agent_config
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching agent config for %s: %s", agent_id, exc)
        raise HTTPException(status_code=500, detail="Error fetching agent configuration")


async def fetch_context_messages(session_id: UUID, limit: int = 5) -> List[Dict[str, Any]]:
    try:
        history = database_service.get_chat_history(str(session_id))[-limit:]
        context: List[Dict[str, Any]] = []

        for offset, item in enumerate(history, start=1):
            context.append(
                {
                    "agent_id": item["agent_id"],
                    "display_name": item.get("display_name", item["agent_id"]),
                    "message": item["message"],
                    "turn_number": item.get("turn_number", offset),
                }
            )

        return context
    except Exception as exc:
        logger.warning("Error fetching context messages for %s: %s", session_id, exc)
        return []


async def save_session_topic(session_id: UUID, topic: str) -> None:
    try:
        redis.set(f"session:{session_id}:topic", topic)
        redis.expire(f"session:{session_id}:topic", 60 * 60 * 24 * 30)
    except Exception as exc:
        logger.warning("Unable to persist topic for session %s: %s", session_id, exc)


async def clear_session_storage(session_id: UUID) -> None:
    session_messages_key = f"session:{session_id}:messages"
    session_topic_key = f"session:{session_id}:topic"

    try:
        raw_entries = redis.lrange(session_messages_key, 0, -1) or []
        legacy_message_keys = [
            message_key
            for raw_entry in raw_entries
            if (message_key := _extract_legacy_message_key(raw_entry))
        ]

        pipeline = redis.pipeline()
        pipeline.delete(session_messages_key)
        pipeline.delete(session_topic_key)
        for message_key in legacy_message_keys:
            pipeline.delete(message_key)
        pipeline.exec()
    except Exception as exc:
        logger.warning("Unable to clear session %s: %s", session_id, exc)
        raise


async def fetch_session_topic(session_id: UUID) -> str:
    try:
        payload = redis.get(f"session:{session_id}:topic")
        if not payload:
            return ""
        return _decode_redis_value(payload)
    except Exception as exc:
        logger.warning("Unable to fetch topic for session %s: %s", session_id, exc)
        return ""


def build_context_prompt(
    topic: str,
    context_messages: List[Dict[str, Any]],
    agent_config: AgentConfig,
    agent_context_matches: Optional[List[Dict[str, Any]]] = None,
) -> str:
    knowledge_block = ""
    retrieval_guidance = ""
    if agent_context_matches:
        context_lines = [str(match.get("data") or "").strip() for match in agent_context_matches if match.get("data")]
        if context_lines:
            knowledge_block = "\n\nRelevant historical speaker context:\n" + "\n".join(
                f"- {line}" for line in context_lines
            )
            retrieval_guidance = (
                "\n\nUse the historical speaker context as background philosophical grounding only. "
                "Do not continue the original source scene, courtroom exchange, interview, or speech verbatim. "
                "Do not address historical interlocutors or named figures from the source material unless they are explicitly part of the current debate. "
                "Translate any retrieved ideas into the present topic and the current panel discussion."
            )

    if not context_messages:
        return (
            f"{agent_config.system_prompt}\n\n"
            f"Discussion topic: {topic}\n"
            f"{knowledge_block}"
            f"{retrieval_guidance}"
            "You are taking the first turn. Provide a clear, substantive response. "
            "Do not prefix your answer with your name, a speaker label, or a turn number. "
            "Do not import historical addressees, scene setup, or source-only references unless the current topic explicitly requires them."
        )

    context_text = "\n".join(
        [f"Turn {msg.get('turn_number', '-')}, {msg.get('display_name', msg['agent_id'])}: {msg['message']}" for msg in context_messages]
    )

    return (
        f"{agent_config.system_prompt}\n\n"
        f"Discussion topic: {topic}\n"
        f"{knowledge_block}"
        f"{retrieval_guidance}\n"
        "Recent discussion context (latest turns):\n"
        f"{context_text}\n\n"
        "Now contribute the next turn. Keep it concise, concrete, and relevant. "
        "Do not prefix your answer with your name, a speaker label, or a turn number. "
        "Do not import historical addressees, scene setup, or source-only references unless the current topic explicitly requires them."
    )


def get_agent_context_matches(query_text: str, agent_id: str) -> List[Dict[str, Any]]:
    try:
        matches = database_service.get_agent_context(query_text=query_text, agent_id=agent_id, top_k=4)
        if matches:
            top_match = matches[0]
            top_metadata = top_match.get("metadata") or {}
            logger.info(
                "Retrieved %s speaker knowledge matches for %s on query=%r (top_score=%s, source=%s, chunk=%s)",
                len(matches),
                agent_id,
                query_text,
                top_match.get("score"),
                top_metadata.get("source_title"),
                top_metadata.get("chunk_index"),
            )
        else:
            logger.info("No speaker knowledge matches found for %s on query=%r", agent_id, query_text)

        return matches
    except Exception as exc:
        logger.warning("Unable to retrieve agent context for %s: %s", agent_id, exc)
        return []


def summarize_vector_telemetry(agent_context_matches: List[Dict[str, Any]]) -> VectorTelemetry:
    sources: List[str] = []
    chunk_ids: List[str] = []
    context_chars = 0

    for match in agent_context_matches:
        metadata = match.get("metadata") or {}
        source_title = str(metadata.get("source_title") or "").strip()
        if source_title and source_title not in sources:
            sources.append(source_title)

        chunk_id = str(match.get("id") or "").strip()
        if chunk_id:
            chunk_ids.append(chunk_id)

        context_chars += len(str(match.get("data") or ""))

    top_score = None
    if agent_context_matches:
        raw_score = agent_context_matches[0].get("score")
        if isinstance(raw_score, (int, float)):
            top_score = float(raw_score)

    return VectorTelemetry(
        used=bool(agent_context_matches),
        match_count=len(agent_context_matches),
        top_score=top_score,
        sources=sources,
        chunk_ids=chunk_ids,
        context_chars=context_chars,
    )


def persist_session_telemetry(session_id: UUID, logic_entropy: float) -> None:
    semantic_overlap = max(0.0, min(1.0, 1.0 - logic_entropy))
    try:
        database_service.set_telemetry_metrics(
            str(session_id),
            logic_entropy=float(logic_entropy),
            semantic_overlap=float(semantic_overlap),
        )
    except Exception as exc:
        logger.warning("Unable to persist session telemetry for %s: %s", session_id, exc)


def sanitize_generated_message(message: str, display_name: str) -> str:
    cleaned = str(message or "").strip()
    if not cleaned:
        return ""

    patterns = [
        rf"^\s*Turn\s+\d+\s*,\s*{re.escape(display_name)}\s*:\s*",
        r"^\s*Turn\s+\d+\s*:\s*",
        rf"^\s*{re.escape(display_name)}\s*:\s*",
    ]

    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE).strip()

    return cleaned


def _configure_pdf_fonts(pdf: FPDF) -> str:
    regular_font = next((path for path in PDF_FONT_SEARCH_PATHS["regular"] if path.exists()), None)
    bold_font = next((path for path in PDF_FONT_SEARCH_PATHS["bold"] if path.exists()), None)
    italic_font = next((path for path in PDF_FONT_SEARCH_PATHS["italic"] if path.exists()), None)

    if regular_font:
        pdf.add_font("TranscriptSans", style="", fname=str(regular_font))
        pdf.add_font("TranscriptSans", style="B", fname=str(bold_font or regular_font))
        pdf.add_font("TranscriptSans", style="I", fname=str(italic_font or regular_font))
        return "TranscriptSans"

    logger.warning("No TTF font found for PDF export; falling back to Helvetica core font")
    return "Helvetica"


def _sanitize_pdf_text(value: Any, *, unicode_font_active: bool) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFKC", text).translate(PDF_TEXT_REPLACEMENTS)
    text = "".join(
        character
        for character in text
        if character == "\n" or unicodedata.category(character) not in {"Cc", "Cf", "Cs", "Co", "Cn", "So"}
    )

    if unicode_font_active:
        return text

    return text.encode("latin-1", errors="replace").decode("latin-1")


def build_chat_messages(
    conversation_messages: List[ChatMessage],
    agent_config: AgentConfig,
    topic: Optional[str] = None,
) -> List[Dict[str, str]]:
    system_prompt = agent_config.system_prompt.strip()
    if topic:
        system_prompt = (
            f"{system_prompt}\n\n"
            f"Debate topic: {topic.strip()}\n"
            "Respond in character, stay concrete, and answer the latest user message directly."
        )

    llm_messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for message in conversation_messages:
        llm_messages.append(
            {
                "role": message.role,
                "content": message.content.strip(),
            }
        )
    return llm_messages


async def call_llm_api(
    prompt: str,
    agent_config: AgentConfig,
    temperature_override: Optional[float] = None,
) -> tuple[str, ExecutionMetrics]:
    api_url = f"{LLM_API_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    effective_temperature = (
        float(temperature_override)
        if isinstance(temperature_override, (int, float))
        else float(agent_config.temperature)
    )
    payload = {
        "model": LLM_MODEL_ID,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": effective_temperature,
        "max_tokens": agent_config.max_tokens,
        "top_p": 0.95,
        "stream": False,
    }

    for attempt in range(LLM_429_MAX_RETRIES + 1):
        try:
            await _wait_for_provider_slot()
            request_started = time.perf_counter()
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(api_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                network_rtt_ms = int((time.perf_counter() - request_started) * 1000)

            if isinstance(data, dict):
                choices = data.get("choices") or []
                if choices:
                    message = choices[0].get("message") or {}
                    content = message.get("content", "")
                    if isinstance(content, list):
                        content = "".join(
                            item.get("text", "") if isinstance(item, dict) else str(item)
                            for item in content
                        )
                    content = str(content).strip()
                    metrics = _extract_execution_metrics(data, response.headers, network_rtt_ms)
                    return content or "I need a moment to process this turn.", metrics

            logger.error("Unexpected LLM API payload: %s", data)
            raise HTTPException(status_code=500, detail="Invalid response from LLM API")
        except HTTPException:
            raise
        except httpx.HTTPStatusError as exc:
            response = exc.response
            if response is not None:
                try:
                    await response.aread()
                except Exception:
                    pass
            error_text = _extract_provider_error_text(response) if response is not None else "Unknown upstream error"
            status_code = response.status_code if response is not None else "unknown"

            if response is not None and response.status_code == 429 and attempt < LLM_429_MAX_RETRIES:
                retry_delay = _parse_retry_after_seconds(response, error_text) or min(2 ** attempt, 8)
                await _sleep_for_retry(retry_delay, attempt + 1)
                continue

            logger.error(
                "LLM provider status error: status=%s, body=%s",
                status_code,
                error_text,
            )
            raise HTTPException(
                status_code=502,
                detail=f"LLM API error ({status_code}): {error_text}",
            )
        except httpx.HTTPError as exc:
            logger.error("LLM provider transport error: %s", exc)
            raise HTTPException(status_code=502, detail="Error communicating with LLM API")

    raise HTTPException(status_code=502, detail="LLM API retry budget exhausted")


def _build_stream_execution_metrics(
    *,
    usage: Optional[Dict[str, Any]],
    headers: httpx.Headers,
    network_rtt_ms: int,
    request_started: float,
    first_token_at: Optional[float],
    generated_message: str,
) -> ExecutionMetrics:
    base_metrics = _extract_execution_metrics(
        {"usage": usage or {}},
        headers,
        network_rtt_ms,
    )
    generation_duration_ms = base_metrics.generation_duration_ms or int((time.perf_counter() - request_started) * 1000)
    completion_tokens = base_metrics.completion_tokens
    if completion_tokens is None and generated_message:
        completion_tokens = max(1, len(generated_message.split()))

    prompt_tokens = base_metrics.prompt_tokens
    total_tokens = base_metrics.total_tokens
    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

    ttft_ms = base_metrics.ttft_ms
    if ttft_ms is None and first_token_at is not None:
        ttft_ms = int((first_token_at - request_started) * 1000)

    tokens_per_second = base_metrics.tokens_per_second
    if not tokens_per_second and completion_tokens and generation_duration_ms > 0:
        tokens_per_second = round(completion_tokens / (generation_duration_ms / 1000), 2)

    return ExecutionMetrics(
        generation_duration_ms=generation_duration_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        tokens_per_second=tokens_per_second,
        queue_time_ms=base_metrics.queue_time_ms,
        prompt_time_ms=base_metrics.prompt_time_ms,
        ttft_ms=ttft_ms,
        network_rtt_ms=network_rtt_ms,
        provider=base_metrics.provider,
        updated_at=datetime.now(timezone.utc),
    )


async def stream_llm_api(
    messages: List[Dict[str, str]],
    agent_config: AgentConfig,
    temperature_override: Optional[float] = None,
    on_complete: Optional[Callable[[str, ExecutionMetrics], Awaitable[None]]] = None,
    on_retry: Optional[Callable[[float, int], Awaitable[None]]] = None,
) -> AsyncIterator[str]:
    api_url = f"{LLM_API_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    effective_temperature = (
        float(temperature_override)
        if isinstance(temperature_override, (int, float))
        else float(agent_config.temperature)
    )
    payload = {
        "model": LLM_MODEL_ID,
        "messages": messages,
        "temperature": effective_temperature,
        "max_tokens": agent_config.max_tokens,
        "top_p": 0.95,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    for attempt in range(LLM_429_MAX_RETRIES + 1):
        try:
            await _wait_for_provider_slot()
            request_started = time.perf_counter()

            async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, read=90.0)) as client:
                async with client.stream("POST", api_url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    network_rtt_ms = int((time.perf_counter() - request_started) * 1000)
                    first_token_at: Optional[float] = None
                    usage_payload: Optional[Dict[str, Any]] = None
                    generated_parts: List[str] = []

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue

                        payload_line = line[5:].strip()
                        if not payload_line:
                            continue
                        if payload_line == "[DONE]":
                            break

                        try:
                            chunk = json.loads(payload_line)
                        except json.JSONDecodeError:
                            logger.debug("Skipping non-JSON stream chunk: %s", payload_line)
                            continue

                        if isinstance(chunk.get("usage"), dict):
                            usage_payload = chunk["usage"]

                        choices = chunk.get("choices") or []
                        if not choices:
                            continue

                        delta = choices[0].get("delta") or {}
                        content = delta.get("content", "")
                        if isinstance(content, list):
                            content = "".join(
                                item.get("text", "") if isinstance(item, dict) else str(item)
                                for item in content
                            )

                        content = str(content)
                        if not content:
                            continue

                        if first_token_at is None:
                            first_token_at = time.perf_counter()

                        generated_parts.append(content)
                        yield content

                    generated_message = "".join(generated_parts).strip()
                    metrics = _build_stream_execution_metrics(
                        usage=usage_payload,
                        headers=response.headers,
                        network_rtt_ms=network_rtt_ms,
                        request_started=request_started,
                        first_token_at=first_token_at,
                        generated_message=generated_message,
                    )
                    if on_complete is not None:
                        await on_complete(generated_message, metrics)
                    return
        except httpx.HTTPStatusError as exc:
            response = exc.response
            if response is not None:
                try:
                    await response.aread()
                except Exception:
                    pass
            error_text = _extract_provider_error_text(response) if response is not None else "Unknown upstream error"
            status_code = response.status_code if response is not None else "unknown"

            if response is not None and response.status_code == 429 and attempt < LLM_429_MAX_RETRIES:
                retry_delay = _parse_retry_after_seconds(response, error_text) or min(2 ** attempt, 8)
                if on_retry is not None:
                    await on_retry(retry_delay, attempt + 1)
                await _sleep_for_retry(retry_delay, attempt + 1)
                continue

            logger.error(
                "Streaming LLM provider status error: status=%s, body=%s",
                status_code,
                error_text,
            )
            raise HTTPException(
                status_code=502,
                detail=f"LLM API error ({status_code}): {error_text}",
            )
        except httpx.HTTPError as exc:
            logger.error("Streaming LLM provider transport error: %s", exc)
            raise HTTPException(status_code=502, detail="Error communicating with LLM API")

    raise HTTPException(status_code=502, detail="LLM API retry budget exhausted")


async def save_message_to_storage(
    *,
    session_id: UUID,
    agent_id: str,
    display_name: str,
    message: str,
    topic: str,
    turn_number: int,
) -> Dict[str, Any]:
    message_id = uuid4()
    created_at = datetime.now(timezone.utc).isoformat()

    record = {
        "id": str(message_id),
        "session_id": str(session_id),
        "agent_id": agent_id,
        "display_name": display_name,
        "message": message,
        "topic": topic,
        "turn_number": turn_number,
        "created_at": created_at,
    }

    try:
        # Redis is the canonical store for live conversation history.
        database_service.append_chat_message(str(session_id), record)

        return record
    except Exception as exc:
        logger.error("Error saving message to Upstash: %s", exc)
        raise HTTPException(status_code=500, detail="Error saving message to Upstash")


async def fetch_session_messages(session_id: UUID) -> List[Dict[str, Any]]:
    raw_entries = database_service.get_chat_history(str(session_id))
    messages: List[Dict[str, Any]] = []

    for index, item in enumerate(raw_entries, start=1):
        if "turn_number" not in item:
            item["turn_number"] = index
        messages.append(item)

    messages.sort(key=lambda item: int(item.get("turn_number", 0)))
    return messages


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
    return await check_services()


@app.get("/telemetry/latest")
async def latest_telemetry() -> Dict[str, Any]:
    metrics = fetch_latest_execution_metrics()
    if metrics is None:
        return {"status": "idle", "metrics": None}
    return {"status": "ok", "metrics": metrics.model_dump(mode="json")}


@app.get("/sessions/{session_id}/topic")
async def get_session_topic(session_id: UUID) -> Dict[str, Any]:
    topic = await fetch_session_topic(session_id)
    return {"session_id": str(session_id), "topic": topic}


@app.post("/sessions/{session_id}/topic")
async def set_session_topic(session_id: UUID, request: SessionTopicUpdateRequest) -> Dict[str, Any]:
    await save_session_topic(session_id, request.topic)
    return {"status": "ok", "session_id": str(session_id), "topic": request.topic}


@app.delete("/sessions/{session_id}")
async def clear_session(session_id: UUID) -> Dict[str, Any]:
    try:
        await clear_session_storage(session_id)
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
        redis.set(f"agent:{request.agent_id}", json.dumps(payload))
        redis.sadd("agents:index", request.agent_id)
        invalidate_agent_registry_cache()
        invalidate_agent_config_cache(request.agent_id)
        return {"status": "ok", "agent_id": request.agent_id}
    except Exception as exc:
        logger.error("Error registering agent %s: %s", request.agent_id, exc)
        raise HTTPException(status_code=500, detail="Error registering agent")


@app.get("/agents")
async def list_agents() -> Dict[str, Any]:
    try:
        cached_agents = get_cached_agent_registry()
        if cached_agents is not None:
            return {"agents": cached_agents}

        ids = redis.smembers("agents:index") or []
        agent_ids = sorted(_decode_redis_value(item) for item in ids)
        agents: List[Dict[str, Any]] = []

        for agent_id in agent_ids:
            payload = redis.get(f"agent:{agent_id}")
            if not payload:
                continue
            agent = _parse_agent_payload(agent_id, _decode_redis_value(payload))
            agents.append(agent.model_dump())

        set_cached_agent_registry(agents)
        return {"agents": agents}
    except Exception as exc:
        logger.error("Error listing agents: %s", exc)
        raise HTTPException(status_code=500, detail="Error retrieving agents")


@app.post("/process-turn", response_model=ProcessTurnResponse)
async def process_turn(request: ProcessTurnRequest) -> ProcessTurnResponse:
    logger.info(
        "Processing turn: session=%s, agent=%s, topic=%s",
        request.session_id,
        request.agent_id,
        request.topic,
    )

    agent_config, context_messages, agent_context_matches = await asyncio.gather(
        fetch_agent_config(request.agent_id),
        fetch_context_messages(request.session_id, limit=5),
        asyncio.to_thread(get_agent_context_matches, request.topic, request.agent_id),
    )
    turn_number = request.turn_number or (len(context_messages) + 1)
    previous_response = ""
    if context_messages:
        previous_response = str(context_messages[-1].get("message", "") or "").strip()

    vector_telemetry = summarize_vector_telemetry(agent_context_matches)
    prompt = build_context_prompt(request.topic, context_messages, agent_config, agent_context_matches)
    generated_message, execution_metrics = await call_llm_api(
        prompt,
        agent_config,
        temperature_override=request.temperature,
    )
    generated_message = sanitize_generated_message(generated_message, agent_config.display_name)
    save_latest_execution_metrics(execution_metrics)
    latency_ms = execution_metrics.generation_duration_ms or execution_metrics.network_rtt_ms or 0
    entropy = calculate_jaccard_entropy(generated_message, previous_response) if previous_response else 0.0
    telemetry = TelemetryData(
        entropy=entropy,
        latency_ms=int(latency_ms),
        word_count=len(generated_message.split()),
        vector=vector_telemetry,
    )
    persist_session_telemetry(request.session_id, entropy)

    stored_message = await save_message_to_storage(
        session_id=request.session_id,
        agent_id=request.agent_id,
        display_name=agent_config.display_name,
        message=generated_message,
        topic=request.topic,
        turn_number=turn_number,
    )

    return ProcessTurnResponse(
        message_id=UUID(str(stored_message["id"])),
        agent_id=request.agent_id,
        display_name=agent_config.display_name,
        message=generated_message,
        turn_number=turn_number,
        created_at=datetime.now(timezone.utc),
        telemetry=telemetry,
        execution_metrics=execution_metrics,
    )


@app.post("/process-turn/stream")
async def process_turn_stream(request: ProcessTurnRequest) -> StreamingResponse:
    logger.info(
        "Streaming turn: session=%s, agent=%s, topic=%s",
        request.session_id,
        request.agent_id,
        request.topic,
    )

    agent_config, context_messages, agent_context_matches = await asyncio.gather(
        fetch_agent_config(request.agent_id),
        fetch_context_messages(request.session_id, limit=5),
        asyncio.to_thread(get_agent_context_matches, request.topic, request.agent_id),
    )
    turn_number = request.turn_number or (len(context_messages) + 1)
    previous_response = ""
    if context_messages:
        previous_response = str(context_messages[-1].get("message", "") or "").strip()

    vector_telemetry = summarize_vector_telemetry(agent_context_matches)
    prompt = build_context_prompt(request.topic, context_messages, agent_config, agent_context_matches)
    final_payload: Optional[ProcessTurnStreamFinal] = None
    event_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()

    async def handle_stream_completion(generated_message: str, execution_metrics: ExecutionMetrics) -> None:
        nonlocal final_payload
        generated_message = sanitize_generated_message(generated_message, agent_config.display_name)
        save_latest_execution_metrics(execution_metrics)
        latency_ms = execution_metrics.generation_duration_ms or execution_metrics.network_rtt_ms or 0
        entropy = calculate_jaccard_entropy(generated_message, previous_response) if previous_response else 0.0
        telemetry = TelemetryData(
            entropy=entropy,
            latency_ms=int(latency_ms),
            word_count=len(generated_message.split()),
            vector=vector_telemetry,
        )
        persist_session_telemetry(request.session_id, entropy)

        stored_message = await save_message_to_storage(
            session_id=request.session_id,
            agent_id=request.agent_id,
            display_name=agent_config.display_name,
            message=generated_message,
            topic=request.topic,
            turn_number=turn_number,
        )

        final_payload = ProcessTurnStreamFinal(
            type="final",
            message_id=UUID(str(stored_message["id"])),
            agent_id=request.agent_id,
            display_name=agent_config.display_name,
            message=generated_message,
            turn_number=turn_number,
            created_at=datetime.now(timezone.utc),
            telemetry=telemetry,
            execution_metrics=execution_metrics,
        )

    async def handle_stream_retry(retry_after_seconds: float, attempt_number: int) -> None:
        retry_message = f"Groq rate limit hit. Retrying in {retry_after_seconds:.1f}s"
        await event_queue.put(
            (ProcessTurnStreamStatus(
                type="status",
                stage="retrying",
                message=retry_message,
                retry_after_seconds=retry_after_seconds,
                attempt_number=attempt_number,
            ).model_dump_json() + "\n").encode("utf-8")
        )

    async def event_stream() -> AsyncIterator[bytes]:
        async def produce_stream_events() -> None:
            try:
                async for chunk in stream_llm_api(
                    [{"role": "user", "content": prompt}],
                    agent_config,
                    temperature_override=request.temperature,
                    on_complete=handle_stream_completion,
                    on_retry=handle_stream_retry,
                ):
                    await event_queue.put(
                        (ProcessTurnStreamChunk(type="chunk", content=chunk).model_dump_json() + "\n").encode("utf-8")
                    )

                if final_payload is not None:
                    await event_queue.put((final_payload.model_dump_json() + "\n").encode("utf-8"))
            finally:
                await event_queue.put(None)

        producer_task = asyncio.create_task(produce_stream_events())

        try:
            while True:
                payload = await event_queue.get()
                if payload is None:
                    break
                yield payload
        finally:
            if not producer_task.done():
                producer_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await producer_task

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    """
    Generate an AI response with Jaccard Similarity Entropy telemetry.
    
    This endpoint produces a response from the specified agent and calculates
    entropy metrics by comparing it against the previous agent's response.
    """
    logger.info(
        "Generating response: session=%s, agent=%s, topic=%s",
        request.session_id,
        request.agent_id,
        request.topic,
    )
    
    start_time = time.time()

    try:
        await save_session_topic(request.session_id, request.topic)
        
        agent_config, context_messages, agent_context_matches = await asyncio.gather(
            fetch_agent_config(request.agent_id),
            fetch_context_messages(request.session_id, limit=5),
            asyncio.to_thread(get_agent_context_matches, request.topic, request.agent_id),
        )
        turn_number = len(context_messages) + 1

        vector_telemetry = summarize_vector_telemetry(agent_context_matches)
        prompt = build_context_prompt(request.topic, context_messages, agent_config, agent_context_matches)
        generated_message, execution_metrics = await call_llm_api(prompt, agent_config)
        save_latest_execution_metrics(execution_metrics)
        
        # Calculate latency in milliseconds
        latency_ms = execution_metrics.generation_duration_ms or int((time.time() - start_time) * 1000)
        
        # Calculate Jaccard Entropy (0.0 for first turn, or compared to previous response)
        if request.previous_response:
            entropy = calculate_jaccard_entropy(generated_message, request.previous_response)
        else:
            entropy = 0.0  # First turn default
        
        # Calculate word count
        word_count = len(generated_message.split())
        
        # Create telemetry object
        telemetry = TelemetryData(
            entropy=entropy,
            latency_ms=latency_ms,
            word_count=word_count,
            vector=vector_telemetry,
        )
        persist_session_telemetry(request.session_id, entropy)
        
        # Persist message to storage
        stored_message = await save_message_to_storage(
            session_id=request.session_id,
            agent_id=request.agent_id,
            display_name=agent_config.display_name,
            message=generated_message,
            topic=request.topic,
            turn_number=turn_number,
        )
        
        return GenerateResponse(
            response=generated_message,
            telemetry=telemetry,
            message_id=UUID(str(stored_message["id"])),
            turn_number=turn_number,
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error in /generate endpoint: %s", exc)
        raise HTTPException(status_code=500, detail="Error generating response")


@app.post("/chat/stream")
async def chat_stream(request: ChatStreamRequest) -> StreamingResponse:
    logger.info(
        "Streaming chat response: session=%s, agent=%s, topic=%s",
        request.session_id,
        request.agent_id,
        request.topic,
    )

    if not request.messages:
        raise HTTPException(status_code=400, detail="At least one message is required")

    agent_config = await fetch_agent_config(request.agent_id)
    llm_messages = build_chat_messages(request.messages, agent_config, topic=request.topic)

    async def handle_stream_completion(
        generated_message: str,
        execution_metrics: ExecutionMetrics,
    ) -> None:
        if generated_message:
            save_latest_execution_metrics(execution_metrics)

        if (
            generated_message
            and request.save_response
            and request.session_id is not None
        ):
            try:
                topic = (request.topic or "Direct chat").strip() or "Direct chat"
                turn_number = len(request.messages)
                await save_message_to_storage(
                    session_id=request.session_id,
                    agent_id=request.agent_id,
                    display_name=agent_config.display_name,
                    message=generated_message,
                    topic=topic,
                    turn_number=turn_number,
                )
            except Exception as exc:
                logger.warning("Unable to persist streamed response: %s", exc)

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in stream_llm_api(
                llm_messages,
                agent_config,
                temperature_override=request.temperature,
                on_complete=handle_stream_completion,
            ):
                if chunk:
                    yield chunk.encode("utf-8")
        except httpx.HTTPStatusError as exc:
            logger.error("Streaming LLM provider status error: %s", exc)
            raise
        except httpx.HTTPError as exc:
            logger.error("Streaming LLM provider transport error: %s", exc)
            raise

    return StreamingResponse(event_stream(), media_type="text/plain; charset=utf-8")


@app.get("/export-pdf/{session_id}")
async def export_pdf(session_id: UUID) -> FileResponse:
    logger.info("Exporting PDF for session: %s", session_id)

    try:
        messages = await fetch_session_messages(session_id)
        if not messages:
            raise HTTPException(status_code=404, detail=f"No messages found for session {session_id}")

        topic = _sanitize_pdf_text(messages[0].get("topic", "N/A"), unicode_font_active=True)

        pdf = FPDF()
        pdf.add_page()
        font_family = _configure_pdf_fonts(pdf)
        unicode_font_active = font_family != "Helvetica"

        pdf.set_font(font_family, "B" if unicode_font_active else "", 16)
        pdf.cell(0, 10, _sanitize_pdf_text("EXHUMED - Discussion Session", unicode_font_active=unicode_font_active), ln=True, align="C")

        pdf.set_font(font_family, "", 10)
        pdf.cell(0, 5, _sanitize_pdf_text(f"Session ID: {session_id}", unicode_font_active=unicode_font_active), ln=True)
        pdf.cell(0, 5, _sanitize_pdf_text(f"Topic: {topic}", unicode_font_active=unicode_font_active), ln=True)
        pdf.ln(5)

        for msg in messages:
            agent_name = _sanitize_pdf_text(
                msg.get("display_name", msg.get("agent_id", "Unknown")),
                unicode_font_active=unicode_font_active,
            )
            turn_number = _sanitize_pdf_text(msg.get("turn_number", "-"), unicode_font_active=unicode_font_active)
            created_at = _sanitize_pdf_text(msg.get("created_at", "Unknown"), unicode_font_active=unicode_font_active)
            text = _sanitize_pdf_text(msg.get("message", ""), unicode_font_active=unicode_font_active)

            pdf.set_font(font_family, "B" if unicode_font_active else "", 10)
            pdf.set_text_color(33, 87, 171)
            pdf.cell(0, 4, f"{agent_name} (Turn {turn_number})", ln=True)

            pdf.set_font(font_family, "I" if unicode_font_active else "", 8)
            pdf.set_text_color(128, 128, 128)
            pdf.cell(0, 3, created_at, ln=True)

            pdf.set_font(font_family, "", 9)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(0, 4, text)
            pdf.ln(2)

        pdf_path = os.path.join(tempfile.gettempdir(), f"exhumed_{session_id}.pdf")
        pdf.output(pdf_path)

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
