from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError


def create_agent_router(*, agent_registry_service: Any, logger: Any, agent_register_request_model: Any) -> APIRouter:
    """Build the router for agent registry mutations and list retrieval."""
    router = APIRouter()

    @router.post("/agents/register")
    async def register_agent(request_data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        """Validate and register an agent definition in the backend registry."""
        try:
            request = agent_register_request_model.model_validate(request_data)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(), body=request_data) from exc
        payload = {
            "display_name": request.display_name,
            "system_prompt": request.system_prompt,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        try:
            await agent_registry_service.register_agent(request.agent_id, payload)
            return {"status": "ok", "agent_id": request.agent_id}
        except Exception as exc:
            logger.error("Error registering agent %s: %s", request.agent_id, exc)
            raise HTTPException(status_code=500, detail="Error registering agent") from exc

    @router.get("/agents")
    async def list_agents() -> Dict[str, Any]:
        """Return the currently registered agent catalog."""
        try:
            agents = await agent_registry_service.list_agents()
            return {"agents": agents}
        except Exception as exc:
            logger.error("Error listing agents: %s", exc)
            raise HTTPException(status_code=500, detail="Error retrieving agents") from exc

    return router
