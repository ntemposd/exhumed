from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional, TypeVar

import httpx


ExecutionMetricsT = TypeVar("ExecutionMetricsT")


def safe_int(value: Any) -> Optional[int]:
    """Best-effort integer coercion for provider timing and token fields."""
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def safe_float(value: Any) -> Optional[float]:
    """Best-effort float coercion for provider timing fields."""
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_ttft_ms(headers: httpx.Headers) -> Optional[int]:
    """Read time-to-first-token from any provider-specific response header variant."""
    candidate_keys = (
        "x-ttft-ms",
        "x-ttft",
        "ttft-ms",
        "openai-processing-ms",
        "x-openai-processing-ms",
    )
    for key in candidate_keys:
        value = headers.get(key)
        parsed = safe_int(value)
        if parsed is not None:
            return parsed
    return None


def estimate_ttft_ms(
    headers: httpx.Headers,
    queue_time_ms: Optional[int],
    prompt_time_ms: Optional[int],
) -> Optional[int]:
    """Infer TTFT when the provider omits a dedicated TTFT header."""
    provider_ttft_ms = extract_ttft_ms(headers)
    if provider_ttft_ms is not None:
        return provider_ttft_ms

    timing_parts = [value for value in (queue_time_ms, prompt_time_ms) if isinstance(value, int)]
    if timing_parts:
        return sum(timing_parts)

    return None


def extract_execution_metrics(
    data: dict[str, Any],
    headers: httpx.Headers,
    network_rtt_ms: int,
    *,
    build_metrics: Callable[..., ExecutionMetricsT],
) -> ExecutionMetricsT:
    """Normalize provider usage and timing fields into the execution metrics model."""
    usage = data.get("usage") if isinstance(data, dict) else {}
    usage = usage if isinstance(usage, dict) else {}

    prompt_tokens = safe_int(usage.get("prompt_tokens"))
    completion_tokens = safe_int(usage.get("completion_tokens"))
    total_tokens = safe_int(usage.get("total_tokens"))
    queue_time_s = safe_float(usage.get("queue_time"))
    prompt_time_s = safe_float(usage.get("prompt_time"))
    generation_duration_s = safe_float(usage.get("total_time")) or safe_float(usage.get("completion_time"))

    queue_time_ms = int(queue_time_s * 1000) if queue_time_s is not None else None
    prompt_time_ms = int(prompt_time_s * 1000) if prompt_time_s is not None else None
    ttft_ms = estimate_ttft_ms(headers, queue_time_ms, prompt_time_ms)
    generation_duration_ms = int(generation_duration_s * 1000) if generation_duration_s is not None else None

    tokens_per_second: Optional[float] = None
    if completion_tokens and generation_duration_s and generation_duration_s > 0:
        tokens_per_second = round(completion_tokens / generation_duration_s, 2)

    return build_metrics(
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


def build_stream_execution_metrics(
    *,
    usage: Optional[dict[str, Any]],
    headers: httpx.Headers,
    network_rtt_ms: int,
    request_started: float,
    first_token_at: Optional[float],
    generated_message: str,
    build_metrics: Callable[..., ExecutionMetricsT],
    monotonic_now: Callable[[], float],
) -> ExecutionMetricsT:
    """Derive execution metrics for streaming completions after the stream closes."""
    base_metrics = extract_execution_metrics(
        {"usage": usage or {}},
        headers,
        network_rtt_ms,
        build_metrics=build_metrics,
    )
    generation_duration_ms = base_metrics.generation_duration_ms or int((monotonic_now() - request_started) * 1000)
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

    return build_metrics(
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
        updated_at=base_metrics.updated_at,
    )