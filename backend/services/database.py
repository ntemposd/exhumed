from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence

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

    def __init__(
        self,
        *,
        redis_client: Redis,
        vector_index: Index,
        embedding_provider: EmbeddingProvider,
        history_ttl_seconds: int = 60 * 60 * 24 * 30,
        telemetry_ttl_seconds: int = 60 * 60 * 24 * 7,
    ) -> None:
        self.redis = redis_client
        self.vector_index = vector_index
        self.embedding_provider = embedding_provider
        self.history_ttl_seconds = history_ttl_seconds
        self.telemetry_ttl_seconds = telemetry_ttl_seconds

    def _history_key(self, session_id: str) -> str:
        return f"session:{session_id}:messages"

    def _telemetry_key(self, session_id: str) -> str:
        return f"session:{session_id}:telemetry"

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
        """Append a single message while preserving the session TTL."""
        key = self._history_key(session_id)
        pipeline = self.redis.pipeline()
        pipeline.rpush(key, json.dumps(dict(message)))
        pipeline.expire(key, self.history_ttl_seconds)
        pipeline.exec()

    def get_chat_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Load and normalize all persisted messages for a session."""
        entries = self.redis.lrange(self._history_key(session_id), 0, -1) or []
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

    def get_recent_chat_history(self, session_id: str, limit: int) -> List[Dict[str, Any]]:
        """Read only the trailing window needed for prompt context or turn-local telemetry."""
        if limit <= 0:
            return []

        entries = self.redis.lrange(self._history_key(session_id), -limit, -1) or []
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
        self.redis.set(key, payload)
        self.redis.expire(key, self.telemetry_ttl_seconds)

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
            matches.append(
                {
                    "id": getattr(item, "id", None),
                    "score": getattr(item, "score", None),
                    "metadata": getattr(item, "metadata", None),
                    "data": getattr(item, "data", None),
                }
            )

        return matches

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
