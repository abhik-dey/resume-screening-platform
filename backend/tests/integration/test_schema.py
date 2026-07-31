"""
Schema integration tests.

These exercise real ORM relationships, cascades, and constraints against
the in-memory SQLite test database — not just "does the table exist."
This is the payoff of the GUID/PORTABLE_JSON type decorators: the exact
same model code that targets Postgres in production is fully exercised
here without needing a live Postgres connection.
"""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domain.entities.job import JobStatus
from app.domain.entities.skill import SkillCategory
from app.domain.entities.user import UserRole
from app.infrastructure.db.models import (
    CandidateModel,
    JobModel,
    RecruiterProfileModel,
    ReportModel,
    ResumeModel,
    ResumeSkillModel,
    ScoreModel,
    SkillModel,
    UserModel,
)
from app.infrastructure.db.models.audit_log import AuditLogModel


async def _make_recruiter(db_session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="recruiter@company.com",
        hashed_password="not-a-real-hash",
        full_name="Recruiter",
        role=UserRole.RECRUITER,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_all_expected_tables_are_registered(test_engine):
    async with test_engine.connect() as conn:
        table_names = await conn.run_sync(lambda sync_conn: sync_conn.dialect.get_table_names(sync_conn))
    expected = {
        "users", "recruiter_profiles", "jobs", "candidates", "resumes",
        "skills", "resume_skills", "scores", "reports", "audit_logs",
    }
    assert expected.issubset(set(table_names))


async def test_recruiter_profile_one_to_one_with_user(db_session):
    user = await _make_recruiter(db_session)
    profile = RecruiterProfileModel(
        id=uuid.uuid4(), user_id=user.id, company_name="Acme Corp", department="Engineering"
    )
    db_session.add(profile)
    await db_session.commit()

    result = await db_session.execute(select(UserModel).where(UserModel.id == user.id))
    fetched_user = result.scalar_one()
    await db_session.refresh(fetched_user, attribute_names=["recruiter_profile"])
    assert fetched_user.recruiter_profile.company_name == "Acme Corp"


async def test_job_creation_and_relationship_to_creator(db_session):
    user = await _make_recruiter(db_session)
    job = JobModel(
        id=uuid.uuid4(),
        created_by=user.id,
        title="Senior Backend Engineer",
        description="Build and scale our API platform.",
        required_skills=["Python", "PostgreSQL"],
        preferred_skills=["Kubernetes"],
        min_experience_years=5,
        status=JobStatus.OPEN,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job, attribute_names=["creator"])

    assert job.creator.email == "recruiter@company.com"
    assert job.required_skills == ["Python", "PostgreSQL"]
    assert job.status == JobStatus.OPEN


async def test_resume_candidate_id_is_nullable_at_upload_time(db_session):
    user = await _make_recruiter(db_session)
    job = JobModel(
        id=uuid.uuid4(), created_by=user.id, title="Data Scientist", description="...",
    )
    db_session.add(job)
    await db_session.commit()

    resume = ResumeModel(
        id=uuid.uuid4(),
        candidate_id=None,  # unresolved until the Resume Parsing Agent runs
        job_id=job.id,
        uploaded_by=user.id,
        storage_path="/storage/resumes/abc123.pdf",
        original_filename="jane_doe_resume.pdf",
    )
    db_session.add(resume)
    await db_session.commit()
    await db_session.refresh(resume)

    assert resume.candidate_id is None
    assert resume.status.value == "uploaded"


async def test_resume_skills_association_with_confidence(db_session):
    user = await _make_recruiter(db_session)
    job = JobModel(id=uuid.uuid4(), created_by=user.id, title="ML Engineer", description="...")
    db_session.add(job)
    await db_session.commit()

    resume = ResumeModel(
        id=uuid.uuid4(), job_id=job.id, uploaded_by=user.id,
        storage_path="/storage/x.pdf", original_filename="x.pdf",
    )
    skill = SkillModel(id=uuid.uuid4(), name="C++", category=SkillCategory.PROGRAMMING)
    db_session.add_all([resume, skill])
    await db_session.commit()

    link = ResumeSkillModel(resume_id=resume.id, skill_id=skill.id, confidence=0.92)
    db_session.add(link)
    await db_session.commit()

    result = await db_session.execute(select(ResumeModel).where(ResumeModel.id == resume.id))
    fetched_resume = result.scalar_one()
    await db_session.refresh(fetched_resume, attribute_names=["skills"])
    assert len(fetched_resume.skills) == 1
    assert fetched_resume.skills[0].confidence == 0.92


async def test_score_is_one_to_one_with_resume(db_session):
    user = await _make_recruiter(db_session)
    job = JobModel(id=uuid.uuid4(), created_by=user.id, title="DevOps Engineer", description="...")
    db_session.add(job)
    await db_session.commit()

    resume = ResumeModel(
        id=uuid.uuid4(), job_id=job.id, uploaded_by=user.id,
        storage_path="/storage/y.pdf", original_filename="y.pdf",
    )
    db_session.add(resume)
    await db_session.commit()

    score = ScoreModel(
        id=uuid.uuid4(), resume_id=resume.id, job_id=job.id, similarity_score=0.87,
        strengths=["Strong Kubernetes experience"], missing_skills=["Terraform"],
    )
    db_session.add(score)
    await db_session.commit()

    # A second score for the same resume must violate the unique constraint.
    duplicate = ScoreModel(id=uuid.uuid4(), resume_id=resume.id, job_id=job.id, similarity_score=0.5)
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_deleting_resume_cascades_to_skills_and_score_but_not_audit_logs(db_session):
    user = await _make_recruiter(db_session)
    job = JobModel(id=uuid.uuid4(), created_by=user.id, title="QA Engineer", description="...")
    db_session.add(job)
    await db_session.commit()

    resume = ResumeModel(
        id=uuid.uuid4(), job_id=job.id, uploaded_by=user.id,
        storage_path="/storage/z.pdf", original_filename="z.pdf",
    )
    skill = SkillModel(id=uuid.uuid4(), name="Selenium", category=SkillCategory.PROGRAMMING)
    db_session.add_all([resume, skill])
    await db_session.commit()

    db_session.add(ResumeSkillModel(resume_id=resume.id, skill_id=skill.id))
    db_session.add(ScoreModel(id=uuid.uuid4(), resume_id=resume.id, job_id=job.id, similarity_score=0.6))
    # Audit log references the resume by string only — no FK relationship.
    db_session.add(
        AuditLogModel(
            id=uuid.uuid4(),
            agent_name="resume_parser",
            input_ref=f"resume:{resume.id}",
            reasoning="Parsed successfully.",
            model_used="gpt-4o-mini",
        )
    )
    await db_session.commit()

    await db_session.delete(resume)
    await db_session.commit()

    remaining_skills = await db_session.execute(
        select(ResumeSkillModel).where(ResumeSkillModel.resume_id == resume.id)
    )
    assert remaining_skills.first() is None

    remaining_scores = await db_session.execute(select(ScoreModel).where(ScoreModel.resume_id == resume.id))
    assert remaining_scores.first() is None

    # The audit log survives — it has no FK to the deleted resume.
    remaining_audit_logs = await db_session.execute(
        select(AuditLogModel).where(AuditLogModel.input_ref == f"resume:{resume.id}")
    )
    assert remaining_audit_logs.scalar_one().reasoning == "Parsed successfully."


async def test_candidate_email_uniqueness(db_session):
    c1 = CandidateModel(id=uuid.uuid4(), full_name="Jane Doe", email="jane@example.com")
    db_session.add(c1)
    await db_session.commit()

    c2 = CandidateModel(id=uuid.uuid4(), full_name="Jane D.", email="jane@example.com")
    db_session.add(c2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_report_relationships(db_session):
    user = await _make_recruiter(db_session)
    job = JobModel(id=uuid.uuid4(), created_by=user.id, title="Product Manager", description="...")
    db_session.add(job)
    await db_session.commit()

    report = ReportModel(
        id=uuid.uuid4(), job_id=job.id, generated_by=user.id,
        file_path="/storage/reports/pm-report.pdf", summary="3 strong candidates identified.",
    )
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report, attribute_names=["job", "generated_by_user"])

    assert report.job.title == "Product Manager"
    assert report.generated_by_user.email == "recruiter@company.com"
