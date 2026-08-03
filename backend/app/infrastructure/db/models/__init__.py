"""
Importing this package registers every ORM model with `Base.metadata`.

Anything that needs the full schema (Alembic's `env.py`, the test suite's
`Base.metadata.create_all`) should import this package rather than
individual model modules — that way, adding a new model file here is
enough; nobody has to remember to update a second list of imports.
"""
from app.infrastructure.db.models.audit_log import AuditLogModel
from app.infrastructure.db.models.candidate import CandidateModel
from app.infrastructure.db.models.interview_question import InterviewQuestionModel
from app.infrastructure.db.models.job import JobModel
from app.infrastructure.db.models.recruiter_profile import RecruiterProfileModel
from app.infrastructure.db.models.report import ReportModel
from app.infrastructure.db.models.resume import ResumeModel
from app.infrastructure.db.models.resume_skill import ResumeSkillModel
from app.infrastructure.db.models.score import ScoreModel
from app.infrastructure.db.models.skill import SkillModel
from app.infrastructure.db.models.user import UserModel

__all__ = [
    "AuditLogModel",
    "CandidateModel",
    "InterviewQuestionModel",
    "JobModel",
    "RecruiterProfileModel",
    "ReportModel",
    "ResumeModel",
    "ResumeSkillModel",
    "ScoreModel",
    "SkillModel",
    "UserModel",
]
