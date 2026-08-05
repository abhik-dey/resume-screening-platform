"""
Resource-level authorization.

CLOSES A REAL GAP flagged in Phase 13: report download checked only that
the caller was authenticated, not that they had any relationship to the
report. Any user could enumerate UUIDs and read every candidate report in
the system — a textbook IDOR, and the most severe issue in the codebase
before this phase.

MODEL
-----
  admin     — full access. Deliberately unrestricted: someone must be able
              to administer the system, and pretending otherwise creates
              workarounds rather than security.
  recruiter — access to what they created. A recruiter who created a job
              can see its resumes, scores, and reports.
  viewer    — read-only, but subject to the SAME ownership rules. "Viewer"
              means "cannot modify", not "can see everything".

The viewer decision matters: it would be easy to treat viewer as a
read-everything role, which would leave the IDOR wide open for the least
privileged role in the system.

Pure and I/O-free so every rule is unit-testable without a database.
"""
from dataclasses import dataclass
from uuid import UUID

from app.domain.entities.user import User, UserRole


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    # Populated only on denial, and deliberately generic — see below.
    reason: str | None = None


def _deny(resource: str) -> AccessDecision:
    # The same message whether the resource doesn't exist or the caller
    # lacks access. Distinguishing them would let an attacker enumerate
    # which report IDs are real.
    return AccessDecision(allowed=False, reason=f"You do not have access to this {resource}")


_ALLOW = AccessDecision(allowed=True)


def can_access_job(user: User, job_created_by: UUID) -> AccessDecision:
    if user.role == UserRole.ADMIN:
        return _ALLOW
    if job_created_by == user.id:
        return _ALLOW
    return _deny("job")


def can_modify_job(user: User, job_created_by: UUID) -> AccessDecision:
    # Viewers can never modify, regardless of ownership.
    if user.role == UserRole.VIEWER:
        return AccessDecision(allowed=False, reason="Viewers cannot modify jobs")
    return can_access_job(user, job_created_by)


def can_access_resume(user: User, resume_uploaded_by: UUID, job_created_by: UUID) -> AccessDecision:
    """A resume is accessible to whoever uploaded it or owns its job.

    Both paths matter: a recruiter may upload to a colleague's job, and the
    job owner needs to see resumes uploaded by others.
    """
    if user.role == UserRole.ADMIN:
        return _ALLOW
    if resume_uploaded_by == user.id or job_created_by == user.id:
        return _ALLOW
    return _deny("resume")


def can_access_report(user: User, report_generated_by: UUID, job_created_by: UUID) -> AccessDecision:
    """THE Phase 13 fix. Reports contain every candidate's name, score, and
    hiring recommendation for a job — the most sensitive artifact here."""
    if user.role == UserRole.ADMIN:
        return _ALLOW
    if report_generated_by == user.id or job_created_by == user.id:
        return _ALLOW
    return _deny("report")


def can_generate_report(user: User, job_created_by: UUID) -> AccessDecision:
    if user.role == UserRole.VIEWER:
        return AccessDecision(allowed=False, reason="Viewers cannot generate reports")
    return can_access_job(user, job_created_by)
