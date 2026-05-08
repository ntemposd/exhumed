from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter


def create_telemetry_router(*, observability_service: Any) -> APIRouter:
    """Build the router that exposes health and telemetry read endpoints."""
    router = APIRouter()

    @router.get("/services-status")
    async def services_status() -> Dict[str, Any]:
        """Return the aggregated runtime health status across backend dependencies."""
        return await observability_service.check_services()

    @router.get("/telemetry/latest")
    async def latest_telemetry() -> Dict[str, Any]:
        """Return the latest execution metrics snapshot recorded by the backend."""
        metrics = observability_service.fetch_latest_execution_metrics()
        if metrics is None:
            return {"status": "idle", "metrics": None}
        return {"status": "ok", "metrics": metrics.model_dump(mode="json")}

    return router
