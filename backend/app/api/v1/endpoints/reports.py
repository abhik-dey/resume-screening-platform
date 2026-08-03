"""Report download endpoint."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.api.deps import get_current_user, get_file_storage, get_report_repository
from app.domain.entities.user import User
from app.domain.interfaces.file_storage import FileStorage
from app.domain.interfaces.report_repository import ReportRepository

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/{report_id}/download")
async def download_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    report_repo: ReportRepository = Depends(get_report_repository),
    storage: FileStorage = Depends(get_file_storage),
) -> Response:
    report = await report_repo.get_by_id(report_id)
    if report is None:
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
