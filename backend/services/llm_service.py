from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional

import httpx
from fastapi import HTTPException


class LLMService:
    """Own outbound provider calls, retry policy, and streaming behavior."""

    def __init__(
        self,
        *,
        api_base_url: str,
        api_key: str,
        model_id: str,
        max_retries: int,
        throttle_seconds: float,
        top_p: float = 0.95,
        execution_metrics_builder: Callable[..., Any],
        extract_execution_metrics: Callable[..., Any],
        build_stream_execution_metrics: Callable[..., Any],
        logger: Any,
        http_client_factory: Callable[..., Any] = httpx.AsyncClient,
        shared_http_client: Optional[httpx.AsyncClient] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        perf_counter: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._api_base_url = api_base_url
        self._api_key = api_key
        self._model_id = model_id
        self._max_retries = max_retries
        self._throttle_seconds = throttle_seconds
        self._top_p = top_p
        self._execution_metrics_builder = execution_metrics_builder
        self._extract_execution_metrics = extract_execution_metrics
        self._build_stream_execution_metrics = build_stream_execution_metrics
        self._logger = logger
        self._http_client_factory = http_client_factory
        self._shared_http_client = shared_http_client
        self._sleep = sleep
        self._perf_counter = perf_counter
        self._provider_gate_lock = asyncio.Lock()
        self._provider_last_request_at = 0.0
        self._provider_cooldown_until = 0.0

    def set_shared_http_client(self, client: Optional[httpx.AsyncClient]) -> None:
        """Attach or clear the lifespan-managed shared HTTP client."""
        self._shared_http_client = client

    def build_chat_messages(
        self,
        conversation_messages: List[Any],
        agent_config: Any,
        topic: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Convert frontend chat history into the provider message format."""
        system_prompt = agent_config.system_prompt.strip()
        if topic:
            system_prompt = (
                f"{system_prompt}\n\n"
                f"Debate topic: {topic.strip()}\n"
                "Respond in character, stay concrete, and answer the latest user message directly."
            )

        llm_messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for message in conversation_messages:
            llm_messages.append({"role": message.role, "content": message.content.strip()})
        return llm_messages

    def _resolve_temperature(self, agent_config: Any, temperature_override: Optional[float] = None) -> float:
        return (
            float(temperature_override)
            if isinstance(temperature_override, (int, float))
            else float(agent_config.temperature)
        )

    def build_provider_request(
        self,
        *,
        messages: List[Dict[str, str]],
        agent_config: Any,
        temperature_override: Optional[float] = None,
        stream: bool,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": self._model_id,
            "messages": messages,
            "temperature": self._resolve_temperature(agent_config, temperature_override),
            "max_tokens": agent_config.max_tokens,
            "top_p": self._top_p,
            "stream": stream,
        }
        if stream:
            body["stream_options"] = {"include_usage": True}

        return {
            "request_url": f"{self._api_base_url}/chat/completions",
            "body": body,
        }

    async def call_llm_api(
        self,
        prompt: str,
        agent_config: Any,
        temperature_override: Optional[float] = None,
    ) -> tuple[str, Any]:
        """Execute a non-streaming completion request with shared retry semantics."""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        provider_request = self.build_provider_request(
            messages=[
                {"role": "system", "content": agent_config.system_prompt.strip()},
                {"role": "user", "content": prompt},
            ],
            agent_config=agent_config,
            temperature_override=temperature_override,
            stream=False,
        )
        api_url = provider_request["request_url"]
        payload = provider_request["body"]

        for attempt in range(self._max_retries + 1):
            try:
                await self._wait_for_provider_slot()
                request_started = self._perf_counter()
                client_context = self._http_client_context(timeout=90.0)
                async with client_context as client:
                    response = await client.post(api_url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    network_rtt_ms = int((self._perf_counter() - request_started) * 1000)

                if isinstance(data, dict):
                    choices = data.get("choices") or []
                    if choices:
                        message = choices[0].get("message") or {}
                        content = message.get("content", "")
                        if isinstance(content, list):
                            content = "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in content)
                        content = str(content).strip()
                        metrics = self._extract_execution_metrics(
                            data,
                            response.headers,
                            network_rtt_ms,
                            build_metrics=self._execution_metrics_builder,
                        )
                        return content or "I need a moment to process this turn.", metrics

                self._logger.error("Unexpected LLM API payload: %s", data)
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
                error_text = self._extract_provider_error_text(response) if response is not None else "Unknown upstream error"
                status_code = response.status_code if response is not None else "unknown"

                if response is not None and response.status_code == 429 and attempt < self._max_retries:
                    retry_delay = self._parse_retry_after_seconds(response, error_text) or min(2 ** attempt, 8)
                    await self._sleep_for_retry(retry_delay, attempt + 1)
                    continue

                self._logger.error("LLM provider status error: status=%s, body=%s", status_code, error_text)
                raise HTTPException(status_code=502, detail=f"LLM API error ({status_code}): {error_text}")
            except httpx.HTTPError as exc:
                self._logger.error("LLM provider transport error: %s", exc)
                raise HTTPException(status_code=502, detail="Error communicating with LLM API")

        raise HTTPException(status_code=502, detail="LLM API retry budget exhausted")

    async def stream_llm_api(
        self,
        messages: List[Dict[str, str]],
        agent_config: Any,
        temperature_override: Optional[float] = None,
        on_complete: Optional[Callable[[str, Any], Awaitable[None]]] = None,
        on_retry: Optional[Callable[[float, int], Awaitable[None]]] = None,
    ) -> AsyncIterator[str]:
        """Stream completion chunks from the provider with shared retry semantics."""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        provider_request = self.build_provider_request(
            messages=messages,
            agent_config=agent_config,
            temperature_override=temperature_override,
            stream=True,
        )
        api_url = provider_request["request_url"]
        payload = provider_request["body"]

        for attempt in range(self._max_retries + 1):
            try:
                await self._wait_for_provider_slot()
                request_started = self._perf_counter()

                client_context = self._http_client_context(timeout=httpx.Timeout(90.0, read=90.0))
                async with client_context as client:
                    async with client.stream("POST", api_url, json=payload, headers=headers) as response:
                        response.raise_for_status()
                        network_rtt_ms = int((self._perf_counter() - request_started) * 1000)
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
                                self._logger.debug("Skipping non-JSON stream chunk: %s", payload_line)
                                continue

                            if isinstance(chunk.get("usage"), dict):
                                usage_payload = chunk["usage"]

                            choices = chunk.get("choices") or []
                            if not choices:
                                continue

                            delta = choices[0].get("delta") or {}
                            content = delta.get("content", "")
                            if isinstance(content, list):
                                content = "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in content)

                            content = str(content)
                            if not content:
                                continue

                            if first_token_at is None:
                                first_token_at = self._perf_counter()

                            generated_parts.append(content)
                            yield content

                        generated_message = "".join(generated_parts).strip()
                        metrics = self._build_stream_execution_metrics(
                            usage=usage_payload,
                            headers=response.headers,
                            network_rtt_ms=network_rtt_ms,
                            request_started=request_started,
                            first_token_at=first_token_at,
                            generated_message=generated_message,
                            build_metrics=self._execution_metrics_builder,
                            monotonic_now=self._perf_counter,
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
                error_text = self._extract_provider_error_text(response) if response is not None else "Unknown upstream error"
                status_code = response.status_code if response is not None else "unknown"

                if response is not None and response.status_code == 429 and attempt < self._max_retries:
                    retry_delay = self._parse_retry_after_seconds(response, error_text) or min(2 ** attempt, 8)
                    if on_retry is not None:
                        await on_retry(retry_delay, attempt + 1)
                    await self._sleep_for_retry(retry_delay, attempt + 1)
                    continue

                self._logger.error("Streaming LLM provider status error: status=%s, body=%s", status_code, error_text)
                raise HTTPException(status_code=502, detail=f"LLM API error ({status_code}): {error_text}")
            except httpx.HTTPError as exc:
                self._logger.error("Streaming LLM provider transport error: %s", exc)
                raise HTTPException(status_code=502, detail="Error communicating with LLM API")

        raise HTTPException(status_code=502, detail="LLM API retry budget exhausted")

    def _extract_provider_error_text(self, response: httpx.Response) -> str:
        try:
            data = response.json()
            if isinstance(data, dict):
                error_payload = data.get("error")
                if isinstance(error_payload, dict):
                    return str(error_payload.get("message") or error_payload.get("error") or error_payload.get("code") or error_payload)
                return str(data.get("message") or data.get("error") or data)
            return str(data)
        except Exception:
            if response is None:
                return "No response body"
            try:
                return response.text[:300]
            except Exception:
                return f"HTTP {response.status_code} with unread or unavailable response body"

    def _parse_retry_after_seconds(self, response: httpx.Response, error_text: str) -> float:
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

    async def _wait_for_provider_slot(self) -> None:
        async with self._provider_gate_lock:
            now = time.monotonic()
            earliest_request_time = max(
                self._provider_cooldown_until,
                self._provider_last_request_at + self._throttle_seconds,
            )
            sleep_for = earliest_request_time - now

            if sleep_for > 0:
                self._logger.info("Throttling LLM provider requests for %.2fs", sleep_for)
                await self._sleep(sleep_for)

            self._provider_last_request_at = time.monotonic()

    async def _register_provider_cooldown(self, delay_seconds: float) -> float:
        bounded_delay = max(0.0, delay_seconds)
        if bounded_delay <= 0:
            return 0.0

        async with self._provider_gate_lock:
            self._provider_cooldown_until = max(self._provider_cooldown_until, time.monotonic() + bounded_delay)

        return bounded_delay

    async def _sleep_for_retry(self, delay_seconds: float, attempt_number: int) -> None:
        retry_delay = await self._register_provider_cooldown(delay_seconds)
        self._logger.warning(
            "LLM provider returned 429, backing off for %.2fs before retry %s/%s",
            retry_delay,
            attempt_number,
            self._max_retries,
        )
        await self._sleep(retry_delay)

    @contextlib.asynccontextmanager
    async def _http_client_context(self, *, timeout: httpx.Timeout | float) -> AsyncIterator[httpx.AsyncClient]:
        if self._shared_http_client is not None:
            yield self._shared_http_client
            return

        async with self._http_client_factory(timeout=timeout) as client:
            yield client