"""Resume endpoints: upload, list, get metadata, download original file."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.api.deps import get_current_user, get_resume_service, require_roles
from app.api.v1.schemas.resume import ResumeResponse
from app.domain.entities.resume import Resume
from app.domain.entities.user import User, UserRole
from app.domain.validation.resume_file import ResumeValidationError
from app.services.resume_service import (
    JobNotFoundError,
    JobNotOpenError,
    ResumeNotFoundError,
    ResumeService,
)

router = APIRouter(tags=["resumes"])

# A conservative content-type map for the download endpoint — derived from
# the file extension we ourselves validated at upload time, not from any
# client-supplied header.
_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.post(
    "/api/v1/jobs/{job_id}/resumes",
    response_model=ResumeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_resume(
    job_id: UUID,
    file: UploadFile,
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.ADMIN)),
    resume_service: ResumeService = Depends(get_resume_service),
) -> Resume:
    content = await file.read()
    try:
        return await resume_service.upload(
            job_id=job_id,
            uploaded_by=current_user.id,
            filename=file.filename or "unnamed",
            content=content,
        )
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except JobNotOpenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ResumeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/api/v1/jobs/{job_id}/resumes", response_model=list[ResumeResponse])
async def list_resumes_for_job(
    job_id: UUID,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    resume_service: ResumeService = Depends(get_resume_service),
) -> list[Resume]:
    return await resume_service.list_resumes_for_job(job_id, skip=skip, limit=limit)


@router.get("/api/v1/resumes/{resume_id}", response_model=ResumeResponse)
async def get_resume(
    resume_id: UUID,
    current_user: User = Depends(get_current_user),
    resume_service: ResumeService = Depends(get_resume_service),
) -> Resume:
    try:
        return await resume_service.get_resume(resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/api/v1/resumes/{resume_id}/download")
async def download_resume(
    resume_id: UUID,
    current_user: User = Depends(get_current_user),
    resume_service: ResumeService = Depends(get_resume_service),
) -> Response:
    try:
        resume, content = await resume_service.download(resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    extension = "." + resume.original_filename.rsplit(".", 1)[-1].lower()
    content_type = _CONTENT_TYPES.get(extension, "application/octet-stream")
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{resume.original_filename}"'},
    )
