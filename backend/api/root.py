from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter


def create_root_router() -> APIRouter:
    router = APIRouter()

    @router.get("/")
    async def root() -> Dict[str, Any]:
        return {
            "name": "EXHUMED",
            "version": "1.1.0",
            "status": "operational",
            "storage": "upstash-redis-vector",
            "endpoints": {
                "process_turn": "/process-turn (POST)",
                "generate_with_telemetry": "/generate (POST) - includes Jaccard Entropy telemetry",
                "chat_stream": "/chat/stream (POST) - plain text streaming for the Next.js frontend",
                "export_pdf": "/export-pdf/{session_id} (GET)",
                "list_agents": "/agents (GET)",
                "register_agent": "/agents/register (POST)",
                "get_session_topic": "/sessions/{session_id}/topic (GET)",
                "set_session_topic": "/sessions/{session_id}/topic (POST)",
            },
        }

    return router
