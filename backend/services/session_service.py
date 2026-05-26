from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import HTTPException


class SessionService:
    """Own session storage, retrieval context, and transcript-oriented formatting concerns."""

    @staticmethod
    def _normalize_topic(value: Any) -> str:
        return str(value or "").strip().casefold()

    def __init__(
        self,
        *,
        redis_client: Any,
        database_service: Any,
        run_blocking_io: Callable[..., Awaitable[Any]],
        decode_value: Callable[[Any], str],
        export_session_pdf: Callable[..., str],
        logger: Any,
    ) -> None:
        self._redis = redis_client
        self._database_service = database_service
        self._run_blocking_io = run_blocking_io
        self._decode_value = decode_value
        self._export_session_pdf = export_session_pdf
        self._logger = logger

    async def fetch_context_messages(
        self,
        session_id: UUID,
        limit: int = 5,
        topic: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Load the recent discussion turns needed to frame the next response."""
        if topic and str(topic).strip():
            raw_entries = await self._run_blocking_io(
                self._database_service.get_recent_chat_history_for_topic,
                str(session_id),
                topic,
                limit,
            )
        else:
            raw_entries = await self._run_blocking_io(self._database_service.get_recent_chat_history, str(session_id), limit)
        messages: List[Dict[str, Any]] = []

        for index, item in enumerate(raw_entries, start=1):
            if "turn_number" not in item:
                item["turn_number"] = index
            messages.append(item)

        messages.sort(key=lambda item: int(item.get("turn_number", 0)))
        return messages

    async def save_session_topic(self, session_id: UUID, topic: str) -> None:
        """Persist the current discussion topic for session resume and export flows."""
        try:
            def _persist_topic() -> None:
                key = f"session:{session_id}:topic"
                # Single pipeline round-trip instead of two sequential SET + EXPIRE calls.
                pipeline = self._redis.pipeline()
                pipeline.set(key, topic)
                pipeline.expire(key, 60 * 60 * 24 * 30)
                pipeline.exec()

            await self._run_blocking_io(_persist_topic)
        except Exception as exc:
            self._logger.warning("Unable to persist topic for session %s: %s", session_id, exc)

    async def clear_session_storage(self, session_id: UUID) -> None:
        """Delete all live storage associated with a session, including legacy keys."""
        session_messages_key = f"session:{session_id}:messages"
        session_topic_key = f"session:{session_id}:topic"

        try:
            def _clear_session_keys() -> None:
                raw_entries = self._redis.lrange(session_messages_key, 0, -1) or []
                legacy_message_keys = [
                    message_key
                    for raw_entry in raw_entries
                    if (message_key := self._extract_legacy_message_key(raw_entry))
                ]

                pipeline = self._redis.pipeline()
                pipeline.delete(session_messages_key)
                pipeline.delete(session_topic_key)
                for message_key in legacy_message_keys:
                    pipeline.delete(message_key)
                pipeline.exec()

            await self._run_blocking_io(_clear_session_keys)
        except Exception as exc:
            self._logger.warning("Unable to clear session %s: %s", session_id, exc)
            raise

    async def fetch_session_topic(self, session_id: UUID) -> str:
        """Return the stored session topic or an empty string when none exists."""
        try:
            payload = await self._run_blocking_io(self._redis.get, f"session:{session_id}:topic")
            if not payload:
                return ""
            return self._decode_value(payload)
        except Exception as exc:
            self._logger.warning("Unable to fetch topic for session %s: %s", session_id, exc)
            return ""

    def build_context_prompt(
        self,
        topic: str,
        context_messages: List[Dict[str, Any]],
        agent_config: Any,
        agent_context_matches: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Assemble the turn prompt from topic, history, and retrieval context."""
        knowledge_block = ""
        retrieval_guidance = ""
        if agent_context_matches:
            context_blocks = [str(match.get("data") or "").strip() for match in agent_context_matches if match.get("data")]
            if context_blocks:
                knowledge_block = "\n\nRelevant historical speaker context:\n\n" + "\n\n".join(
                    f"[{index + 1}] {block}" for index, block in enumerate(context_blocks)
                )
                retrieval_guidance = (
                    "\n\nYour response must be grounded in the passages above - these are your authentic words and thinking. "
                    "Reason from the ideas and principles in those passages when addressing the current topic. "
                    "Do not draw on general or popular knowledge about yourself beyond what the passages establish. "
                    "Do not reproduce the original scene, courtroom exchange, interview, or speech verbatim. "
                    "Do not address historical interlocutors from the source material unless they are part of this debate. "
                    "Apply the retrieved ideas directly to the current topic and panel discussion."
                )
        else:
            retrieval_guidance = (
                "\n\nNo source passages were retrieved for this turn. "
                "Respond using only the documented philosophy, principles, and positions "
                "that define your persona. Do not speculate beyond what is historically established."
            )

        if not context_messages:
            return (
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
            f"Discussion topic: {topic}\n"
            f"{knowledge_block}"
            f"{retrieval_guidance}\n"
            "Recent discussion context (for awareness only — do NOT echo or mirror):\n"
            f"{context_text}\n\n"
            "Now contribute the next turn. CRITICAL: Your response must begin from your OWN distinct perspective and voice. "
            "Do NOT open with the same framing, phrasing, or angle as any previous speaker. "
            "Do NOT rephrase or restate what another speaker already said before adding your view. "
            "Jump directly into your own thought — your opening sentence must be entirely different in structure and content from any prior turn. "
            "Keep it concise, concrete, and relevant. "
            "Do not prefix your answer with your name, a speaker label, or a turn number. "
            "Do not import historical addressees, scene setup, or source-only references unless the current topic explicitly requires them."
        )

    def get_agent_context_matches(self, query_text: str, agent_id: str) -> List[Dict[str, Any]]:
        """Fetch and log the Vector matches that will ground a speaker's next turn."""
        try:
            matches = self._database_service.get_agent_context(query_text=query_text, agent_id=agent_id, top_k=4)
            if matches:
                top_match = matches[0]
                top_metadata = top_match.get("metadata") or {}
                self._logger.info(
                    "Retrieved %s speaker knowledge matches for %s on query=%r (top_score=%s, source=%s, chunk=%s)",
                    len(matches),
                    agent_id,
                    query_text,
                    top_match.get("score"),
                    top_metadata.get("source_title"),
                    top_metadata.get("chunk_index"),
                )
            else:
                self._logger.info("No speaker knowledge matches found for %s on query=%r", agent_id, query_text)

            return matches
        except Exception as exc:
            self._logger.warning("Unable to retrieve agent context for %s: %s", agent_id, exc)
            return []

    def summarize_vector_telemetry(self, agent_context_matches: List[Dict[str, Any]], *, build_vector_telemetry: Callable[..., Any]) -> Any:
        """Reduce raw Vector matches to the telemetry surfaced to the frontend."""
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

        return build_vector_telemetry(
            used=bool(agent_context_matches),
            match_count=len(agent_context_matches),
            top_score=top_score,
            sources=sources,
            chunk_ids=chunk_ids,
            context_chars=context_chars,
        )

    def persist_session_telemetry(self, session_id: UUID, logic_entropy: float) -> None:
        """Persist the derived entropy metrics for the session sidebar and exports."""
        semantic_overlap = max(0.0, min(1.0, 1.0 - logic_entropy))
        try:
            self._database_service.set_telemetry_metrics(
                str(session_id),
                logic_entropy=float(logic_entropy),
                semantic_overlap=float(semantic_overlap),
            )
        except Exception as exc:
            self._logger.warning("Unable to persist session telemetry for %s: %s", session_id, exc)

    async def persist_session_telemetry_async(self, session_id: UUID, logic_entropy: float) -> None:
        """Async wrapper around the blocking session telemetry write path."""
        await self._run_blocking_io(self.persist_session_telemetry, session_id, logic_entropy)

    def sanitize_generated_message(self, message: str, display_name: str) -> str:
        """Strip model-added speaker labels so persisted turns stay presentation-neutral."""
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

    async def save_message_to_storage(
        self,
        *,
        session_id: UUID,
        agent_id: str,
        display_name: str,
        message: str,
        topic: str,
        turn_number: int,
    ) -> Dict[str, Any]:
        """Persist a completed turn to Redis-backed session history."""
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
            await self._run_blocking_io(self._database_service.store_chat_message, str(session_id), record)
            return record
        except Exception as exc:
            self._logger.error("Error saving message to Upstash: %s", exc)
            raise HTTPException(status_code=500, detail="Error saving message to Upstash")

    async def fetch_session_messages(self, session_id: UUID) -> List[Dict[str, Any]]:
        """Load the full normalized transcript for a session."""
        raw_entries = await self._run_blocking_io(self._database_service.get_chat_history, str(session_id))
        messages: List[Dict[str, Any]] = []

        for index, item in enumerate(raw_entries, start=1):
            if "turn_number" not in item:
                item["turn_number"] = index
            messages.append(item)

        messages.sort(key=lambda item: int(item.get("turn_number", 0)))
        return messages

    async def export_pdf_file(self, session_id: UUID, *, topic: Optional[str] = None) -> str:
        """Render a persisted session transcript to PDF and return its temporary file path."""
        active_topic = topic if str(topic or "").strip() else await self.fetch_session_topic(session_id)
        messages = await self.fetch_session_messages(session_id)
        normalized_active_topic = self._normalize_topic(active_topic)
        if normalized_active_topic:
            messages = [
                message
                for message in messages
                if self._normalize_topic(message.get("topic")) == normalized_active_topic
            ]
        if not messages:
            raise HTTPException(status_code=404, detail=f"No messages found for session {session_id}")
        return self._export_session_pdf(messages, session_id, logger=self._logger)

    def _extract_legacy_message_key(self, raw_entry: Any) -> Optional[str]:
        decoded_entry = self._decode_value(raw_entry)

        try:
            item = json.loads(decoded_entry)
            if isinstance(item, dict) and "message" in item:
                return None
        except json.JSONDecodeError:
            pass

        return f"message:{decoded_entry}" if decoded_entry else None