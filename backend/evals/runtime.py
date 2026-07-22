from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from functools import partial
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

try:
    from backend.composition import build_runtime_services
    from backend.settings import load_settings
    from backend.utils.execution_metrics import build_stream_execution_metrics, extract_execution_metrics
    from backend.utils.pdf_export import export_session_pdf
    from backend.utils.text_metrics import calculate_jaccard_entropy
except ModuleNotFoundError:  # pragma: no cover
    from composition import build_runtime_services
    from settings import load_settings
    from utils.execution_metrics import build_stream_execution_metrics, extract_execution_metrics
    from utils.pdf_export import export_session_pdf
    from utils.text_metrics import calculate_jaccard_entropy


class _AgentConfig(BaseModel):
    agent_id: str
    display_name: str
    system_prompt: str
    temperature: float = 0.7
    max_tokens: int = 512


class _ExecutionMetrics(BaseModel):
    generation_duration_ms: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    tokens_per_second: Optional[float] = None
    queue_time_ms: Optional[int] = None
    prompt_time_ms: Optional[int] = None
    ttft_ms: Optional[int] = None
    network_rtt_ms: Optional[int] = None
    provider: str = "llm"
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class _AnswerEvalScores(BaseModel):
    grounding: float
    persona: float
    debate: float


class _AnswerJudgeTelemetry(BaseModel):
    faithfulness: float
    persona: float
    faithfulness_notes: str = ""
    persona_notes: str = ""


class _VectorTelemetry(BaseModel):
    used: bool
    match_count: int
    top_score: Optional[float] = None
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    chunk_ids: List[str] = Field(default_factory=list)
    context_chars: int = 0


class _TelemetryData(BaseModel):
    entropy: float
    latency_ms: int
    word_count: int
    vector: Optional[_VectorTelemetry] = None
    scores: Optional[_AnswerEvalScores] = None
    judge: Optional[_AnswerJudgeTelemetry] = None


class _ProcessTurnResponse(BaseModel):
    message_id: UUID
    agent_id: str
    display_name: str
    message: str
    turn_number: int
    created_at: datetime
    telemetry: _TelemetryData
    execution_metrics: _ExecutionMetrics


class _GenerateResponse(BaseModel):
    response: str
    telemetry: _TelemetryData
    message_id: Optional[UUID] = None
    turn_number: Optional[int] = None


class _StreamChunk(BaseModel):
    type: str = "chunk"
    content: str


class _StreamStatus(BaseModel):
    type: str = "status"
    stage: str
    message: str
    retry_after_seconds: Optional[float] = None
    attempt_number: Optional[int] = None


class _StreamFinal(BaseModel):
    type: str = "final"
    message_id: UUID
    agent_id: str
    display_name: str
    message: str
    turn_number: int
    created_at: datetime
    telemetry: _TelemetryData
    execution_metrics: _ExecutionMetrics


def _decode_redis_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _parse_agent_payload(agent_id: str, raw: str) -> _AgentConfig:
    payload = json.loads(raw) if isinstance(raw, str) else dict(raw)
    return _AgentConfig(
        agent_id=agent_id,
        display_name=payload["display_name"],
        system_prompt=payload["system_prompt"],
        temperature=float(payload.get("temperature", 0.7)),
        max_tokens=int(payload.get("max_tokens", 512)),
    )


async def _run_blocking_io(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return await asyncio.to_thread(partial(func, *args, **kwargs))


def build_eval_services(*, logger: logging.Logger | None = None) -> Dict[str, Any]:
    """Bootstrap API runtime services for offline eval scripts (no FastAPI app)."""
    active_logger = logger or logging.getLogger("backend.evals")
    settings = load_settings()
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
        llm_debate_max_tokens=max(50, settings.llm.debate_max_tokens),
        llm_retrieval_top_k=max(1, settings.llm.retrieval_top_k),
        llm_retrieval_weak_top_k_bonus=max(0, settings.llm.retrieval_weak_top_k_bonus),
        llm_context_turn_limit=max(1, settings.llm.context_turn_limit),
        llm_prompt_max_source_chunk_chars=max(200, settings.llm.prompt_max_source_chunk_chars),
        llm_prompt_max_context_turn_chars=max(120, settings.llm.prompt_max_context_turn_chars),
        agent_registry_cache_ttl_seconds=settings.storage.agent_registry_cache_ttl_seconds,
        agent_config_cache_ttl_seconds=settings.storage.agent_config_cache_ttl_seconds,
        session_max_messages=settings.storage.session_max_messages,
        prompt_capture_backend="off",
        prompt_capture_max_entries=settings.storage.prompt_capture_max_entries,
        decode_redis_value=_decode_redis_value,
        parse_agent_payload=_parse_agent_payload,
        run_blocking_io=_run_blocking_io,
        calculate_entropy=calculate_jaccard_entropy,
        execution_metrics_model=_ExecutionMetrics,
        extract_execution_metrics=extract_execution_metrics,
        build_stream_execution_metrics=build_stream_execution_metrics,
        telemetry_model=_TelemetryData,
        vector_telemetry_model=_VectorTelemetry,
        process_turn_response_model=_ProcessTurnResponse,
        process_turn_stream_chunk_model=_StreamChunk,
        process_turn_stream_status_model=_StreamStatus,
        process_turn_stream_final_model=_StreamFinal,
        generate_response_model=_GenerateResponse,
        streaming_response_factory=lambda *args, **kwargs: None,
        export_session_pdf=export_session_pdf,
        prompt_capture_log_path=settings.base_dir / "backend" / "logs" / "provider_prompt_captures.jsonl",
        logger=active_logger,
    )
