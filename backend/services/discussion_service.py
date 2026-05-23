from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Optional
from uuid import UUID

from fastapi import HTTPException


class DiscussionService:
    """Coordinate route-level discussion flows so FastAPI handlers stay declarative."""

    def __init__(
        self,
        *,
        turn_workflow_service: Any,
        session_service: Any,
        llm_service: Any,
        fetch_agent_config: Callable[[str], Awaitable[Any]],
        save_latest_execution_metrics: Callable[[Any], Awaitable[None]],
        save_prompt_capture: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
        process_turn_response_model: Callable[..., Any],
        process_turn_stream_chunk_model: Callable[..., Any],
        process_turn_stream_status_model: Callable[..., Any],
        process_turn_stream_final_model: Callable[..., Any],
        generate_response_model: Callable[..., Any],
        streaming_response_factory: Callable[..., Any],
        vector_telemetry_model: Callable[..., Any],
        logger: Any,
        utcnow: Callable[[], Any],
    ) -> None:
        self._turn_workflow_service = turn_workflow_service
        self._session_service = session_service
        self._llm_service = llm_service
        self._fetch_agent_config = fetch_agent_config
        self._save_latest_execution_metrics = save_latest_execution_metrics
        self._save_prompt_capture = save_prompt_capture
        self._process_turn_response_model = process_turn_response_model
        self._process_turn_stream_chunk_model = process_turn_stream_chunk_model
        self._process_turn_stream_status_model = process_turn_stream_status_model
        self._process_turn_stream_final_model = process_turn_stream_final_model
        self._generate_response_model = generate_response_model
        self._streaming_response_factory = streaming_response_factory
        self._vector_telemetry_model = vector_telemetry_model
        self._logger = logger
        self._utcnow = utcnow

    async def _capture_provider_request(
        self,
        *,
        route: str,
        session_id: Any,
        topic: str,
        turn_number: int,
        agent_config: Any,
        prompt: str,
        context_messages: list[dict[str, Any]],
        agent_context_matches: list[dict[str, Any]],
        temperature_override: Optional[float],
        stream: bool,
    ) -> None:
        """Persist a local JSONL record of the exact provider request built for this turn."""
        if self._save_prompt_capture is None:
            return

        provider_request = self._llm_service.build_provider_request(
            messages=[
                {"role": "system", "content": str(getattr(agent_config, "system_prompt", "") or "").strip()},
                {"role": "user", "content": prompt},
            ],
            agent_config=agent_config,
            temperature_override=temperature_override,
            stream=stream,
        )
        vector_context = [
            {
                "id": match.get("id"),
                "score": match.get("score"),
                "source_title": (match.get("metadata") or {}).get("source_title"),
                "data": match.get("data") or "",
            }
            for match in agent_context_matches
        ]
        await self._save_prompt_capture(
            {
                "route": route,
                "provider_mode": "stream" if stream else "non-stream",
                "session_id": str(session_id),
                "agent_id": getattr(agent_config, "agent_id", None),
                "display_name": getattr(agent_config, "display_name", ""),
                "topic": topic,
                "turn_number": turn_number,
                "context_turns": len(context_messages),
                "vector_matches": len(agent_context_matches),
                "context_messages": [dict(message) for message in context_messages],
                "vector_context": vector_context,
                "prompt": prompt,
                "provider_request": provider_request,
                "provider_url": provider_request["request_url"].rsplit("/chat/completions", 1)[0],
                "model_id": provider_request["body"].get("model"),
                "temperature": provider_request["body"].get("temperature"),
                "max_tokens": provider_request["body"].get("max_tokens"),
            }
        )

    async def process_turn(self, request: Any) -> Any:
        """Generate and persist a complete non-streaming debate turn."""
        self._logger.info(
            "Processing turn: session=%s, agent=%s, topic=%s",
            request.session_id,
            request.agent_id,
            request.topic,
        )
        await self._session_service.save_session_topic(request.session_id, request.topic)

        agent_config, context_messages, agent_context_matches, previous_response = await self._turn_workflow_service.prepare_turn_inputs(
            session_id=request.session_id,
            agent_id=request.agent_id,
            topic=request.topic,
        )
        turn_number = request.turn_number or (len(context_messages) + 1)

        vector_telemetry = self._session_service.summarize_vector_telemetry(
            agent_context_matches,
            build_vector_telemetry=self._vector_telemetry_model,
        )
        prompt = self._session_service.build_context_prompt(request.topic, context_messages, agent_config, agent_context_matches)
        await self._capture_provider_request(
            route="process-turn",
            session_id=request.session_id,
            topic=request.topic,
            turn_number=turn_number,
            agent_config=agent_config,
            prompt=prompt,
            context_messages=context_messages,
            agent_context_matches=agent_context_matches,
            temperature_override=request.temperature,
            stream=False,
        )
        generated_message, execution_metrics = await self._llm_service.call_llm_api(
            prompt,
            agent_config,
            temperature_override=request.temperature,
        )
        generated_message, telemetry, stored_message = await self._turn_workflow_service.finalize_generated_turn(
            session_id=request.session_id,
            agent_id=request.agent_id,
            display_name=agent_config.display_name,
            generated_message=generated_message,
            topic=request.topic,
            turn_number=turn_number,
            previous_response=previous_response,
            vector_telemetry=vector_telemetry,
            execution_metrics=execution_metrics,
        )

        return self._process_turn_response_model(
            message_id=UUID(str(stored_message["id"])),
            agent_id=request.agent_id,
            display_name=agent_config.display_name,
            message=generated_message,
            turn_number=turn_number,
            created_at=self._utcnow(),
            telemetry=telemetry,
            execution_metrics=execution_metrics,
        )

    async def process_turn_stream(self, request: Any) -> Any:
        """Stream a debate turn token-by-token and finalize persistence on completion."""
        self._logger.info(
            "Streaming turn: session=%s, agent=%s, topic=%s",
            request.session_id,
            request.agent_id,
            request.topic,
        )
        await self._session_service.save_session_topic(request.session_id, request.topic)

        agent_config, context_messages, agent_context_matches, previous_response = await self._turn_workflow_service.prepare_turn_inputs(
            session_id=request.session_id,
            agent_id=request.agent_id,
            topic=request.topic,
        )
        turn_number = request.turn_number or (len(context_messages) + 1)

        vector_telemetry = self._session_service.summarize_vector_telemetry(
            agent_context_matches,
            build_vector_telemetry=self._vector_telemetry_model,
        )
        prompt = self._session_service.build_context_prompt(request.topic, context_messages, agent_config, agent_context_matches)
        await self._capture_provider_request(
            route="process-turn/stream",
            session_id=request.session_id,
            topic=request.topic,
            turn_number=turn_number,
            agent_config=agent_config,
            prompt=prompt,
            context_messages=context_messages,
            agent_context_matches=agent_context_matches,
            temperature_override=request.temperature,
            stream=True,
        )
        final_payload: Optional[Any] = None
        event_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()

        async def handle_stream_completion(generated_message: str, execution_metrics: Any) -> None:
            nonlocal final_payload
            generated_message, telemetry, stored_message = await self._turn_workflow_service.finalize_generated_turn(
                session_id=request.session_id,
                agent_id=request.agent_id,
                display_name=agent_config.display_name,
                generated_message=generated_message,
                topic=request.topic,
                turn_number=turn_number,
                previous_response=previous_response,
                vector_telemetry=vector_telemetry,
                execution_metrics=execution_metrics,
            )

            final_payload = self._process_turn_stream_final_model(
                type="final",
                message_id=UUID(str(stored_message["id"])),
                agent_id=request.agent_id,
                display_name=agent_config.display_name,
                message=generated_message,
                turn_number=turn_number,
                created_at=self._utcnow(),
                telemetry=telemetry,
                execution_metrics=execution_metrics,
            )

        async def handle_stream_retry(retry_after_seconds: float, attempt_number: int) -> None:
            retry_message = f"Groq rate limit hit. Retrying in {retry_after_seconds:.1f}s"
            await event_queue.put(
                (self._process_turn_stream_status_model(
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
                    async for chunk in self._llm_service.stream_llm_api(
                        [
                            {"role": "system", "content": str(getattr(agent_config, "system_prompt", "") or "").strip()},
                            {"role": "user", "content": prompt},
                        ],
                        agent_config,
                        temperature_override=request.temperature,
                        on_complete=handle_stream_completion,
                        on_retry=handle_stream_retry,
                    ):
                        await event_queue.put(
                            (self._process_turn_stream_chunk_model(type="chunk", content=chunk).model_dump_json() + "\n").encode("utf-8")
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

        return self._streaming_response_factory(event_stream(), media_type="application/x-ndjson")

    async def generate(self, request: Any) -> Any:
        """Generate a response plus entropy telemetry for the legacy non-streaming route."""
        self._logger.info(
            "Generating response: session=%s, agent=%s, topic=%s",
            request.session_id,
            request.agent_id,
            request.topic,
        )

        start_time = time.time()
        await self._session_service.save_session_topic(request.session_id, request.topic)

        agent_config, context_messages, agent_context_matches, _ = await self._turn_workflow_service.prepare_turn_inputs(
            session_id=request.session_id,
            agent_id=request.agent_id,
            topic=request.topic,
        )
        turn_number = len(context_messages) + 1

        vector_telemetry = self._session_service.summarize_vector_telemetry(
            agent_context_matches,
            build_vector_telemetry=self._vector_telemetry_model,
        )
        prompt = self._session_service.build_context_prompt(request.topic, context_messages, agent_config, agent_context_matches)
        await self._capture_provider_request(
            route="generate",
            session_id=request.session_id,
            topic=request.topic,
            turn_number=turn_number,
            agent_config=agent_config,
            prompt=prompt,
            context_messages=context_messages,
            agent_context_matches=agent_context_matches,
            temperature_override=None,
            stream=False,
        )
        generated_message, execution_metrics = await self._llm_service.call_llm_api(prompt, agent_config)
        generated_message, telemetry, stored_message = await self._turn_workflow_service.finalize_generated_turn(
            session_id=request.session_id,
            agent_id=request.agent_id,
            display_name=agent_config.display_name,
            generated_message=generated_message,
            topic=request.topic,
            turn_number=turn_number,
            previous_response=request.previous_response or "",
            vector_telemetry=vector_telemetry,
            execution_metrics=execution_metrics,
            latency_ms_fallback=int((time.time() - start_time) * 1000),
        )

        return self._generate_response_model(
            response=generated_message,
            telemetry=telemetry,
            message_id=UUID(str(stored_message["id"])),
            turn_number=turn_number,
        )

    async def chat_stream(self, request: Any) -> Any:
        """Stream a plain chat completion for the frontend chat workbench."""
        self._logger.info(
            "Streaming chat response: session=%s, agent=%s, topic=%s",
            request.session_id,
            request.agent_id,
            request.topic,
        )

        if not request.messages:
            raise HTTPException(status_code=400, detail="At least one message is required")

        agent_config = await self._fetch_agent_config(request.agent_id)
        llm_messages = self._llm_service.build_chat_messages(request.messages, agent_config, topic=request.topic)

        async def handle_stream_completion(generated_message: str, execution_metrics: Any) -> None:
            if generated_message:
                await self._save_latest_execution_metrics(execution_metrics)

            if generated_message and request.save_response and request.session_id is not None:
                try:
                    topic = (request.topic or "Direct chat").strip() or "Direct chat"
                    turn_number = len(request.messages)
                    await self._session_service.save_message_to_storage(
                        session_id=request.session_id,
                        agent_id=request.agent_id,
                        display_name=agent_config.display_name,
                        message=generated_message,
                        topic=topic,
                        turn_number=turn_number,
                    )
                except Exception as exc:
                    self._logger.warning("Unable to persist streamed response: %s", exc)

        async def event_stream() -> AsyncIterator[bytes]:
            async for chunk in self._llm_service.stream_llm_api(
                llm_messages,
                agent_config,
                temperature_override=request.temperature,
                on_complete=handle_stream_completion,
            ):
                if chunk:
                    yield chunk.encode("utf-8")

        return self._streaming_response_factory(event_stream(), media_type="text/plain; charset=utf-8")