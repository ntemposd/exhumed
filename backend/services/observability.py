from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar

import httpx


ExecutionMetricsT = TypeVar("ExecutionMetricsT")


class ObservabilityService:
    """Own health checks and latest-metrics polling state for the backend."""

    def __init__(
        self,
        *,
        redis_client: Any,
        vector_index: Any,
        decode_value: Callable[[Any], str],
        run_blocking_io: Callable[..., Awaitable[Any]],
        execution_metrics_model: Any,
        llm_api_base_url: str,
        llm_api_key: str,
        logger: Any,
        http_client_factory: Callable[..., Any] = httpx.AsyncClient,
        shared_http_client: Optional[httpx.AsyncClient] = None,
        perf_counter: Callable[[], float] = time.perf_counter,
        utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._redis = redis_client
        self._vector_index = vector_index
        self._decode_value = decode_value
        self._run_blocking_io = run_blocking_io
        self._execution_metrics_model = execution_metrics_model
        self._llm_api_base_url = llm_api_base_url
        self._llm_api_key = llm_api_key
        self._logger = logger
        self._http_client_factory = http_client_factory
        self._shared_http_client = shared_http_client
        self._perf_counter = perf_counter
        self._utcnow = utcnow

    def set_shared_http_client(self, client: Optional[httpx.AsyncClient]) -> None:
        """Attach or clear the lifespan-managed shared HTTP client."""
        self._shared_http_client = client

    def save_latest_execution_metrics(self, metrics: Any) -> None:
        """Persist the most recent execution metrics snapshot for telemetry polling."""
        try:
            self._redis.set("telemetry:latest", metrics.model_dump_json())
        except Exception as exc:
            self._logger.warning("Unable to persist latest execution telemetry: %s", exc)

    async def save_latest_execution_metrics_async(self, metrics: Any) -> None:
        """Async wrapper around latest-metrics persistence."""
        await self._run_blocking_io(self.save_latest_execution_metrics, metrics)

    def fetch_latest_execution_metrics(self) -> Optional[ExecutionMetricsT]:
        """Load the latest execution metrics snapshot if one has been recorded."""
        try:
            payload = self._redis.get("telemetry:latest")
            if not payload:
                return None
            raw = json.loads(self._decode_value(payload))
            if isinstance(raw, dict):
                return self._execution_metrics_model.model_validate(raw)
        except Exception as exc:
            self._logger.warning("Unable to load latest execution telemetry: %s", exc)
        return None

    async def check_services(self) -> Dict[str, Any]:
        """Run lightweight health checks against Redis, Vector, and the inference provider."""
        services = []

        redis_started = self._perf_counter()
        try:
            await self._run_blocking_io(self._redis.ping)
            redis_latency_ms = int((self._perf_counter() - redis_started) * 1000)
            services.append({"name": "Redis", "status": "ONLINE", "latency_ms": redis_latency_ms, "detail": None})
        except Exception as exc:
            self._logger.warning("Redis health check failed: %s", exc)
            services.append({"name": "Redis", "status": "OFFLINE", "latency_ms": None, "detail": str(exc)[:160]})

        vector_started = self._perf_counter()
        try:
            await self._run_blocking_io(self._vector_index.info)
            vector_latency_ms = int((self._perf_counter() - vector_started) * 1000)
            services.append({"name": "Vector", "status": "ONLINE", "latency_ms": vector_latency_ms, "detail": None})
        except Exception as exc:
            self._logger.warning("Upstash Vector health check failed: %s", exc)
            services.append({"name": "Vector", "status": "OFFLINE", "latency_ms": None, "detail": str(exc)[:160]})

        inference_started = self._perf_counter()
        try:
            headers = {"Authorization": f"Bearer {self._llm_api_key}"}
            if self._shared_http_client is not None:
                response = await self._shared_http_client.get(
                    f"{self._llm_api_base_url}/models",
                    headers=headers,
                    timeout=15.0,
                )
                response.raise_for_status()
            else:
                async with self._http_client_factory(timeout=15.0) as client:
                    response = await client.get(f"{self._llm_api_base_url}/models", headers=headers)
                    response.raise_for_status()
            inference_latency_ms = int((self._perf_counter() - inference_started) * 1000)
            services.append({"name": "Inference", "status": "ONLINE", "latency_ms": inference_latency_ms, "detail": None})
        except Exception as exc:
            self._logger.warning("Inference health check failed: %s", exc)
            services.append({"name": "Inference", "status": "OFFLINE", "latency_ms": None, "detail": str(exc)[:160]})

        overall_status = "OPTIMAL" if all(service["status"] == "ONLINE" for service in services) else "DEGRADED"
        return {
            "status": overall_status,
            "services": services,
            "checked_at": self._utcnow().isoformat(),
        }