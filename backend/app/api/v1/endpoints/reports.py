"""Report download endpoint."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.api.deps import (
    get_current_user,
    get_file_storage,
    get_job_repository,
    get_report_repository,
)
from app.domain.entities.user import User
from app.domain.interfaces.file_storage import FileStorage
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.report_repository import ReportRepository
from app.domain.security.authorization import can_access_report

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/{report_id}/download")
async def download_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    report_repo: ReportRepository = Depends(get_report_repository),
    job_repo: JobRepository = Depends(get_job_repository),
    storage: FileStorage = Depends(get_file_storage),
) -> Response:
    report = await report_repo.get_by_id(report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Report {report_id} not found"
        )

    # PHASE 19 FIX for the IDOR flagged in Phase 13: before this, any
    # authenticated user could download any report by guessing its UUID.
    # Reports contain every candidate's name, score, and recommendation.
    job = await job_repo.get_by_id(report.job_id)
    decision = can_access_report(
        current_user,
        report_generated_by=report.generated_by,
        job_created_by=job.created_by if job else report.generated_by,
    )
    if not decision.allowed:
        # 404, not 403: a 403 confirms the report exists, letting an
        # attacker enumerate valid IDs.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Report {report_id} not found"
        )

    try:
        content = await storage.read(report.file_path)
    except FileNotFoundError as exc:
        # The database row exists but the file is gone — a real operational
        # failure worth distinguishing from "no such report".
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} exists but its file is missing from storage",
        ) from exc

    filename = f"candidate-report-{report_id}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
