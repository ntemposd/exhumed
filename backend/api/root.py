from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

try:
    from backend.version import APP_VERSION
except ModuleNotFoundError:
    from version import APP_VERSION


def create_root_router() -> APIRouter:
    """Build the root router that exposes the backend capability summary."""
    router = APIRouter()

    @router.get("/")
    async def root() -> Dict[str, Any]:
        """Return a lightweight summary of service identity and public endpoints."""
        return {
            "name": "EXHUMED",
            "version": APP_VERSION,
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
