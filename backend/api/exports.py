from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


def create_export_router(*, session_service, logger) -> APIRouter:
    """Build the router that exposes transcript export endpoints."""
    router = APIRouter()

    @router.get("/export-pdf/{session_id}")
    async def export_pdf(session_id: UUID, topic: Optional[str] = None) -> FileResponse:
        """Generate and return a PDF transcript for the requested session."""
        logger.info("Exporting PDF for session: %s (topic=%r)", session_id, topic)

        try:
            pdf_path = await session_service.export_pdf_file(session_id, topic=topic)
            return FileResponse(
                path=pdf_path,
                filename=f"exhumed_discussion_{session_id}.pdf",
                media_type="application/pdf",
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Error generating PDF for %s: %s", session_id, exc)
            raise HTTPException(status_code=500, detail="Error generating PDF export") from exc

    return router
