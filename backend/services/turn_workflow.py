from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from uuid import UUID


class TurnWorkflowService:
    """Coordinates the shared turn lifecycle used by the generation endpoints."""

    def __init__(
        self,
        *,
        fetch_agent_config: Callable[[str], Awaitable[Any]],
        fetch_context_messages: Callable[[UUID, int], Awaitable[List[Dict[str, Any]]]],
        get_agent_context_matches: Callable[[str, str], List[Dict[str, Any]]],
        sanitize_generated_message: Callable[[str, str], str],
        save_latest_execution_metrics: Callable[[Any], Awaitable[None]],
        persist_session_telemetry: Callable[[UUID, float], Awaitable[None]],
        save_message_to_storage: Callable[..., Awaitable[Dict[str, Any]]],
        calculate_entropy: Callable[[str, str], float],
        build_telemetry: Callable[..., Any],
    ) -> None:
        self.fetch_agent_config = fetch_agent_config
        self.fetch_context_messages = fetch_context_messages
        self.get_agent_context_matches = get_agent_context_matches
        self.sanitize_generated_message = sanitize_generated_message
        self.save_latest_execution_metrics = save_latest_execution_metrics
        self.persist_session_telemetry = persist_session_telemetry
        self.save_message_to_storage = save_message_to_storage
        self.calculate_entropy = calculate_entropy
        self.build_telemetry = build_telemetry

    async def prepare_turn_inputs(
        self,
        *,
        session_id: UUID,
        agent_id: str,
        topic: str,
        context_limit: int = 5,
    ) -> Tuple[Any, List[Dict[str, Any]], List[Dict[str, Any]], str]:
        """Load the agent config, recent discussion context, and speaker knowledge in parallel."""
        agent_config, context_messages, agent_context_matches = await asyncio.gather(
            self.fetch_agent_config(agent_id),
            self.fetch_context_messages(session_id, context_limit),
            asyncio.to_thread(self.get_agent_context_matches, topic, agent_id),
        )
        previous_response = ""
        if context_messages:
            previous_response = str(context_messages[-1].get("message", "") or "").strip()

        return agent_config, context_messages, agent_context_matches, previous_response

    async def finalize_generated_turn(
        self,
        *,
        session_id: UUID,
        agent_id: str,
        display_name: str,
        generated_message: str,
        topic: str,
        turn_number: int,
        previous_response: str,
        vector_telemetry: Any,
        execution_metrics: Any,
        latency_ms_fallback: Optional[int] = None,
    ) -> Tuple[str, Any, Dict[str, Any]]:
        """Apply post-generation cleanup, telemetry derivation, and message persistence."""
        sanitized_message = self.sanitize_generated_message(generated_message, display_name)
        await self.save_latest_execution_metrics(execution_metrics)

        latency_ms = (
            getattr(execution_metrics, "generation_duration_ms", None)
            or getattr(execution_metrics, "network_rtt_ms", None)
            or latency_ms_fallback
            or 0
        )
        entropy = self.calculate_entropy(sanitized_message, previous_response) if previous_response else 0.0
        telemetry = self.build_telemetry(
            entropy=entropy,
            latency_ms=int(latency_ms),
            word_count=len(sanitized_message.split()),
            vector=vector_telemetry,
        )
        await self.persist_session_telemetry(session_id, entropy)
        stored_message = await self.save_message_to_storage(
            session_id=session_id,
            agent_id=agent_id,
            display_name=display_name,
            message=sanitized_message,
            topic=topic,
            turn_number=turn_number,
        )

        return sanitized_message, telemetry, stored_message