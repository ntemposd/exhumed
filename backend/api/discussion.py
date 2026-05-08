from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError


def create_discussion_router(
    *,
    discussion_service,
    process_turn_request_model,
    process_turn_response_model,
    generate_request_model,
    generate_response_model,
    chat_stream_request_model,
) -> APIRouter:
    """Build the router for debate turns, streaming responses, and chat endpoints."""
    router = APIRouter()

    @router.post("/process-turn", response_model=process_turn_response_model)
    async def process_turn(request_data: Dict[str, Any] = Body(...)):
        """Validate and execute a single non-streaming debate turn."""
        try:
            request = process_turn_request_model.model_validate(request_data)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(), body=request_data) from exc
        return await discussion_service.process_turn(request)

    @router.post("/process-turn/stream")
    async def process_turn_stream(request_data: Dict[str, Any] = Body(...)):
        """Validate and stream a debate turn token-by-token to the frontend."""
        try:
            request = process_turn_request_model.model_validate(request_data)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(), body=request_data) from exc
        return await discussion_service.process_turn_stream(request)

    @router.post("/generate", response_model=generate_response_model)
    async def generate(request_data: Dict[str, Any] = Body(...)):
        """Validate and execute the legacy telemetry-bearing generation endpoint."""
        try:
            request = generate_request_model.model_validate(request_data)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(), body=request_data) from exc
        return await discussion_service.generate(request)

    @router.post("/chat/stream")
    async def chat_stream(request_data: Dict[str, Any] = Body(...)):
        """Validate and stream a plain chat completion for the workbench UI."""
        try:
            request = chat_stream_request_model.model_validate(request_data)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(), body=request_data) from exc
        return await discussion_service.chat_stream(request)

    return router
