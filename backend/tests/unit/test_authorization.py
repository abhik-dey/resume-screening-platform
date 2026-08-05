"""
Authorization tests.

The Phase 13 IDOR is the specific bug these close: any authenticated user
could download any report by guessing its UUID.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.domain.entities.user import User, UserRole
from app.domain.security.authorization import (
    can_access_job,
    can_access_report,
    can_access_resume,
    can_generate_report,
    can_modify_job,
)


def _user(role: UserRole, user_id=None) -> User:
    return User(
        id=user_id or uuid.uuid4(),
        email="u@example.com",
        hashed_password="x",
        full_name="User",
        role=role,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def owner():
    return _user(UserRole.RECRUITER)


@pytest.fixture
def stranger():
    return _user(UserRole.RECRUITER)


@pytest.fixture
def admin():
    return _user(UserRole.ADMIN)


@pytest.fixture
def viewer():
    return _user(UserRole.VIEWER)


# --- The Phase 13 IDOR ---

def test_stranger_cannot_access_another_users_report(owner, stranger):
    # THE bug: before this, any authenticated user could read any report.
    decision = can_access_report(
        stranger, report_generated_by=owner.id, job_created_by=owner.id
    )
    assert decision.allowed is False


def test_report_owner_can_access_their_report(owner):
    assert can_access_report(owner, owner.id, owner.id).allowed is True


def test_job_owner_can_access_reports_generated_by_others(owner, stranger):
    # A colleague generating a report on your job shouldn't lock you out.
    assert can_access_report(owner, report_generated_by=stranger.id, job_created_by=owner.id).allowed


def test_admin_can_access_any_report(admin, owner):
    assert can_access_report(admin, owner.id, owner.id).allowed is True


def test_viewer_is_subject_to_the_same_ownership_rules(viewer, owner):
    # "Viewer" means cannot modify, NOT can see everything. Treating it as
    # read-everything would leave the IDOR open for the least privileged role.
    assert can_access_report(viewer, owner.id, owner.id).allowed is False


def test_viewer_can_access_their_own_job_report(viewer):
    assert can_access_report(viewer, viewer.id, viewer.id).allowed is True


def test_denial_reasons_do_not_reveal_resource_existence(stranger, owner):
    # Distinguishing "doesn't exist" from "no access" lets an attacker
    # enumerate valid IDs.
    decision = can_access_report(stranger, owner.id, owner.id)
    assert "do not have access" in decision.reason
    assert "not found" not in decision.reason.lower()


# --- Jobs ---

def test_job_owner_has_access(owner):
    assert can_access_job(owner, owner.id).allowed is True


def test_stranger_has_no_job_access(stranger, owner):
    assert can_access_job(stranger, owner.id).allowed is False


def test_admin_has_job_access(admin, owner):
    assert can_access_job(admin, owner.id).allowed is True


def test_viewer_cannot_modify_even_their_own_job(viewer):
    assert can_access_job(viewer, viewer.id).allowed is True
    assert can_modify_job(viewer, viewer.id).allowed is False


def test_viewer_cannot_generate_reports(viewer):
    assert can_generate_report(viewer, viewer.id).allowed is False


# --- Resumes ---

def test_uploader_can_access_the_resume_they_uploaded(owner, stranger):
    assert can_access_resume(owner, resume_uploaded_by=owner.id, job_created_by=stranger.id).allowed


def test_job_owner_can_access_resumes_uploaded_by_others(owner, stranger):
    assert can_access_resume(owner, resume_uploaded_by=stranger.id, job_created_by=owner.id).allowed


def test_unrelated_user_cannot_access_a_resume(owner, stranger):
    third_party = _user(UserRole.RECRUITER)
    assert (
        can_access_resume(third_party, resume_uploaded_by=owner.id, job_created_by=stranger.id).allowed
        is False
    )


def test_admin_can_access_any_resume(admin, owner):
    assert can_access_resume(admin, owner.id, owner.id).allowed is True
