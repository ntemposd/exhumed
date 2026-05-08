from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError


def create_session_router(*, session_service: Any, logger: Any, session_topic_update_request_model: Any) -> APIRouter:
    """Build the router for session topic reads, writes, and session cleanup."""
    router = APIRouter()

    @router.get("/sessions/{session_id}/topic")
    async def get_session_topic(session_id: UUID) -> Dict[str, Any]:
        """Fetch the persisted topic label for the requested session."""
        topic = await session_service.fetch_session_topic(session_id)
        return {"session_id": str(session_id), "topic": topic}

    @router.post("/sessions/{session_id}/topic")
    async def set_session_topic(session_id: UUID, request_data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        """Validate and persist a new topic label for the requested session."""
        try:
            request = session_topic_update_request_model.model_validate(request_data)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(), body=request_data) from exc
        await session_service.save_session_topic(session_id, request.topic)
        return {"status": "ok", "session_id": str(session_id), "topic": request.topic}

    @router.delete("/sessions/{session_id}")
    async def clear_session(session_id: UUID) -> Dict[str, Any]:
        """Delete all live backend state associated with the requested session."""
        try:
            await session_service.clear_session_storage(session_id)
            return {"status": "ok", "session_id": str(session_id)}
        except Exception as exc:
            logger.error("Error clearing session %s: %s", session_id, exc)
            raise HTTPException(status_code=500, detail="Error clearing session") from exc

    return router
