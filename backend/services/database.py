from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from upstash_redis import Redis
from upstash_vector.errors import UpstashError
from upstash_vector import Index


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> List[float]:
        ...


class SentenceTransformerEmbeddingProvider:
    """Lazy sentence-transformer wrapper used only when local embeddings are needed."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = None

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is required for Vector querying. "
                    "Install it in the backend environment or inject a custom embedding provider."
                ) from exc

            self._model = SentenceTransformer(self.model_name)

        return self._model

    def embed(self, text: str) -> List[float]:
        model = self._load_model()
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist() if hasattr(vector, "tolist") else list(vector)


@dataclass
class TelemetrySnapshot:
    logic_entropy: Optional[float] = None
    semantic_overlap: Optional[float] = None


class DatabaseService:
    """Encapsulates Redis-backed session state and Vector-backed speaker retrieval."""

    _VECTOR_SCORE_THRESHOLD: float = 0.60

    def __init__(
        self,
        *,
        redis_client: Redis,
        vector_index: Index,
        embedding_provider: EmbeddingProvider,
        history_ttl_seconds: int = 60 * 60 * 24 * 30,
        telemetry_ttl_seconds: int = 60 * 60 * 24 * 7,
        max_messages: Optional[int] = 200,
    ) -> None:
        self.redis = redis_client
        self.vector_index = vector_index
        self.embedding_provider = embedding_provider
        self.history_ttl_seconds = history_ttl_seconds
        self.telemetry_ttl_seconds = telemetry_ttl_seconds
        # Cap on messages stored per session list. When exceeded, the oldest
        # messages are trimmed via LTRIM so the list never grows unbounded.
        # Set to None to disable trimming.
        self.max_messages = max_messages

    def _history_key(self, session_id: str) -> str:
        return f"session:{session_id}:messages"

    def _telemetry_key(self, session_id: str) -> str:
        return f"session:{session_id}:telemetry"

    @staticmethod
    def _chunk_id(agent_id: str, source_slug: str, chunk_index: int) -> str:
        return f"{agent_id}:{source_slug}:{chunk_index:04d}"

    @staticmethod
    def _decode_redis_value(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    @staticmethod
    def _coerce_history(history: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [dict(item) for item in history]

    @staticmethod
    def _escape_filter_value(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    @staticmethod
    def _coerce_optional_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _parse_chunk_locator(cls, match: Dict[str, Any], agent_id: str) -> Tuple[Optional[str], Optional[int]]:
        metadata = match.get("metadata") or {}
        source_slug = str(metadata.get("source_slug") or "").strip() or None
        chunk_index = cls._coerce_optional_int(metadata.get("chunk_index"))

        if source_slug and chunk_index is not None:
            return source_slug, chunk_index

        raw_id = str(match.get("id") or "").strip()
        id_pattern = rf"^{re.escape(agent_id)}:(?P<source_slug>[^:]+):(?P<chunk_index>\d+)$"
        id_match = re.match(id_pattern, raw_id)
        if not id_match:
            return source_slug, chunk_index

        return (
            source_slug or id_match.group("source_slug"),
            chunk_index if chunk_index is not None else int(id_match.group("chunk_index")),
        )

    @staticmethod
    def _coerce_vector_match(item: Any) -> Dict[str, Any]:
        if isinstance(item, dict):
            return {
                "id": item.get("id"),
                "score": item.get("score"),
                "metadata": item.get("metadata") or {},
                "data": item.get("data") or "",
            }

        return {
            "id": getattr(item, "id", None),
            "score": getattr(item, "score", None),
            "metadata": getattr(item, "metadata", None) or {},
            "data": getattr(item, "data", None) or "",
        }

    def _fetch_vectors_by_ids(self, ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        if not ids or not hasattr(self.vector_index, "fetch"):
            return {}

        raw_result = self.vector_index.fetch(ids=list(ids))
        if isinstance(raw_result, dict):
            raw_vectors = raw_result.get("vectors") or raw_result.get("items") or []
        else:
            raw_vectors = getattr(raw_result, "vectors", raw_result)

        vectors_by_id: Dict[str, Dict[str, Any]] = {}
        for item in raw_vectors or []:
            coerced = self._coerce_vector_match(item)
            vector_id = str(coerced.get("id") or "").strip()
            if vector_id:
                vectors_by_id[vector_id] = coerced

        return vectors_by_id

    def _enrich_matches_with_neighbors(
        self,
        matches: List[Dict[str, Any]],
        *,
        agent_id: str,
        neighbor_window: int,
    ) -> List[Dict[str, Any]]:
        if neighbor_window <= 0 or not matches:
            return matches

        neighbor_ids: List[str] = []
        for match in matches:
            source_slug, chunk_index = self._parse_chunk_locator(match, agent_id)
            if not source_slug or chunk_index is None:
                continue

            for offset in range(-neighbor_window, neighbor_window + 1):
                candidate_index = chunk_index + offset
                if candidate_index < 1:
                    continue
                neighbor_ids.append(self._chunk_id(agent_id, source_slug, candidate_index))

        fetched_vectors = self._fetch_vectors_by_ids(list(dict.fromkeys(neighbor_ids)))
        if not fetched_vectors:
            return matches

        enriched_matches: List[Dict[str, Any]] = []
        for match in matches:
            source_slug, chunk_index = self._parse_chunk_locator(match, agent_id)
            if not source_slug or chunk_index is None:
                enriched_matches.append(match)
                continue

            ordered_ids = [
                self._chunk_id(agent_id, source_slug, candidate_index)
                for candidate_index in range(max(1, chunk_index - neighbor_window), chunk_index + neighbor_window + 1)
            ]

            ordered_chunks: List[str] = []
            neighbor_chunk_ids: List[str] = []
            for vector_id in ordered_ids:
                if vector_id == str(match.get("id") or ""):
                    candidate = match
                else:
                    candidate = fetched_vectors.get(vector_id)
                if not candidate:
                    continue

                candidate_text = str(candidate.get("data") or "").strip()
                if not candidate_text:
                    continue

                ordered_chunks.append(candidate_text)
                neighbor_chunk_ids.append(vector_id)

            if not ordered_chunks:
                enriched_matches.append(match)
                continue

            metadata = dict(match.get("metadata") or {})
            metadata["source_slug"] = metadata.get("source_slug") or source_slug
            metadata["chunk_index"] = metadata.get("chunk_index") or chunk_index
            metadata["neighbor_chunk_ids"] = neighbor_chunk_ids
            metadata["retrieval_text_mode"] = "neighbor_enriched"

            enriched_matches.append(
                {
                    **match,
                    "metadata": metadata,
                    "data": "\n\n".join(ordered_chunks),
                }
            )

        return enriched_matches

    @staticmethod
    def _normalize_topic(value: Any) -> str:
        return str(value or "").strip().casefold()

    def _parse_history_entries(self, entries: Sequence[Any]) -> List[Dict[str, Any]]:
        history: List[Dict[str, Any]] = []

        for raw_entry in entries:
            try:
                item = json.loads(self._decode_redis_value(raw_entry))
            except json.JSONDecodeError:
                continue

            if isinstance(item, dict):
                history.append(dict(item))

        history.sort(key=lambda item: int(item.get("turn_number", 0)))
        return history

    def set_chat_history(self, session_id: str, history: Sequence[Dict[str, Any]]) -> None:
        """Replace the full stored message history for a session."""
        key = self._history_key(session_id)
        pipeline = self.redis.pipeline()
        pipeline.delete(key)
        normalized_history = self._coerce_history(history)
        if normalized_history:
            pipeline.rpush(key, *[json.dumps(item) for item in normalized_history])
        pipeline.expire(key, self.history_ttl_seconds)
        pipeline.exec()

    def store_chat_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """Append a single message while preserving the session TTL.

        When max_messages is set the list is trimmed from the left so only the
        most recent N messages are retained, preventing unbounded Redis list
        growth on ephemeral hosting platforms such as Railway.
        """
        key = self._history_key(session_id)
        pipeline = self.redis.pipeline()
        pipeline.rpush(key, json.dumps(dict(message)))
        if self.max_messages and self.max_messages > 0:
            # Keep only the newest max_messages entries.
            pipeline.ltrim(key, -self.max_messages, -1)
        pipeline.expire(key, self.history_ttl_seconds)
        pipeline.exec()

    def get_chat_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Load and normalize all persisted messages for a session."""
        entries = self.redis.lrange(self._history_key(session_id), 0, -1) or []
        return self._parse_history_entries(entries)

    def get_recent_chat_history(self, session_id: str, limit: int) -> List[Dict[str, Any]]:
        """Read only the trailing window needed for prompt context or turn-local telemetry."""
        if limit <= 0:
            return []

        entries = self.redis.lrange(self._history_key(session_id), -limit, -1) or []
        return self._parse_history_entries(entries)

    def get_recent_chat_history_for_topic(self, session_id: str, topic: str, limit: int) -> List[Dict[str, Any]]:
        """Return the most recent turns for the active topic only."""
        if limit <= 0:
            return []

        normalized_topic = self._normalize_topic(topic)
        if not normalized_topic:
            return self.get_recent_chat_history(session_id, limit)

        history = self.get_chat_history(session_id)
        filtered_history = [
            item
            for item in history
            if self._normalize_topic(item.get("topic")) == normalized_topic
        ]
        return filtered_history[-limit:]

    def append_chat_message(self, session_id: str, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Append one message and return the normalized session history."""
        self.store_chat_message(session_id, message)
        return self.get_chat_history(session_id)

    def set_telemetry_metrics(
        self,
        session_id: str,
        *,
        logic_entropy: float,
        semantic_overlap: float,
    ) -> None:
        """Persist the latest derived telemetry snapshot for a session."""
        payload = json.dumps(
            {
                "logic_entropy": float(logic_entropy),
                "semantic_overlap": float(semantic_overlap),
            }
        )
        key = self._telemetry_key(session_id)
        # Single pipeline round-trip instead of two sequential SET + EXPIRE calls.
        pipeline = self.redis.pipeline()
        pipeline.set(key, payload)
        pipeline.expire(key, self.telemetry_ttl_seconds)
        pipeline.exec()

    def get_telemetry_metrics(self, session_id: str) -> TelemetrySnapshot:
        """Return the stored telemetry snapshot for a session if one exists."""
        payload = self.redis.get(self._telemetry_key(session_id))
        if not payload:
            return TelemetrySnapshot()

        raw = json.loads(self._decode_redis_value(payload))
        if not isinstance(raw, dict):
            return TelemetrySnapshot()

        logic_entropy = raw.get("logic_entropy")
        semantic_overlap = raw.get("semantic_overlap")

        return TelemetrySnapshot(
            logic_entropy=float(logic_entropy) if logic_entropy is not None else None,
            semantic_overlap=float(semantic_overlap) if semantic_overlap is not None else None,
        )

    def get_agent_context(
        self,
        query_text: str,
        agent_id: str,
        *,
        top_k: int = 5,
        include_metadata: bool = True,
        include_data: bool = True,
        neighbor_window: int = 1,
    ) -> List[Dict[str, Any]]:
        """Retrieve speaker-specific knowledge chunks from Upstash Vector."""
        filter_expression = f"agent_id = '{self._escape_filter_value(agent_id)}'"
        try:
            results = self.vector_index.query(
                data=query_text,
                top_k=top_k,
                include_metadata=include_metadata,
                include_data=include_data,
                filter=filter_expression,
            )
        except UpstashError as exc:
            error_message = str(exc).lower()
            if "embedding" not in error_message and "data" not in error_message:
                raise

            query_embedding = self.embedding_provider.embed(query_text)
            results = self.vector_index.query(
                vector=query_embedding,
                top_k=top_k,
                include_metadata=include_metadata,
                include_data=include_data,
                filter=filter_expression,
            )

        matches: List[Dict[str, Any]] = []
        for item in results:
            matches.append(self._coerce_vector_match(item))

        matches = [match for match in matches if (match.get("score") or 0.0) >= self._VECTOR_SCORE_THRESHOLD]
        if not matches:
            return []

        return self._enrich_matches_with_neighbors(matches, agent_id=agent_id, neighbor_window=neighbor_window)

    def build_system_prompt(
        self,
        *,
        base_system_prompt: str,
        session_id: str,
        query_text: str,
        agent_id: str,
        history_limit: int = 5,
        context_limit: int = 5,
    ) -> str:
        """Compose a retrieval-augmented system prompt from history and Vector matches."""
        history = self.get_chat_history(session_id)[-history_limit:]
        context_matches = self.get_agent_context(query_text, agent_id, top_k=context_limit)

        history_block = "\n".join(
            f"- {entry.get('display_name') or entry.get('role') or entry.get('agent_id')}: {entry.get('message') or entry.get('content') or ''}".strip()
            for entry in history
        )
        context_block = "\n".join(
            f"- {match.get('data') or ''}".strip()
            for match in context_matches
            if match.get("data")
        )

        prompt_sections = [base_system_prompt.strip()]

        if history_block:
            prompt_sections.append("Recent chat history:\n" + history_block)

        if context_block:
            prompt_sections.append("Relevant speaker context:\n" + context_block)

        prompt_sections.append(f"Current user query:\n{query_text.strip()}")
        return "\n\n".join(section for section in prompt_sections if section)


def create_database_service(
    *,
    embedding_provider: Optional[EmbeddingProvider] = None,
) -> DatabaseService:
    """Construct the default database service from environment-backed Upstash clients."""
    redis_url = os.environ["UPSTASH_REDIS_REST_URL"]
    redis_token = os.environ["UPSTASH_REDIS_REST_TOKEN"]
    vector_url = os.environ["UPSTASH_VECTOR_REST_URL"]
    vector_token = os.environ["UPSTASH_VECTOR_REST_TOKEN"]

    return DatabaseService(
        redis_client=Redis(url=redis_url, token=redis_token),
        vector_index=Index(url=vector_url, token=vector_token),
        embedding_provider=embedding_provider or SentenceTransformerEmbeddingProvider(),
    )
