from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException


def create_session_router(*, session_service: Any, logger: Any, session_topic_update_request_model: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/sessions/{session_id}/topic")
    async def get_session_topic(session_id: UUID) -> Dict[str, Any]:
        topic = await session_service.fetch_session_topic(session_id)
        return {"session_id": str(session_id), "topic": topic}

    @router.post("/sessions/{session_id}/topic")
    async def set_session_topic(session_id: UUID, request_data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        request = session_topic_update_request_model.model_validate(request_data)
        await session_service.save_session_topic(session_id, request.topic)
        return {"status": "ok", "session_id": str(session_id), "topic": request.topic}

    @router.delete("/sessions/{session_id}")
    async def clear_session(session_id: UUID) -> Dict[str, Any]:
        try:
            await session_service.clear_session_storage(session_id)
            return {"status": "ok", "session_id": str(session_id)}
        except Exception as exc:
            logger.error("Error clearing session %s: %s", session_id, exc)
            raise HTTPException(status_code=500, detail="Error clearing session") from exc

    return router
