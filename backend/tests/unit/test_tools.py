"""
Tool implementation tests.

Weighted toward the constrained tools — email never sending, filesystem
staying sandboxed, LinkedIn never contacting LinkedIn — because those
constraints are the design, and a regression in one is a real incident
rather than a broken feature.
"""
from pathlib import Path

import pytest

from app.domain.tools.base import ToolError
from app.infrastructure.tools.external_tools import (
    CalendarAvailabilityTool,
    EmailDraftTool,
    FilesystemReadTool,
    GitHubProfileTool,
    LinkedInProfileTool,
)

# --- Email: never sends ---

async def test_email_draft_never_reports_as_sent():
    tool = EmailDraftTool()
    result = await tool.execute(
        {"recipient_name": "Jane Doe", "subject": "Interview", "body": "Hello"}
    )
    assert result.success is True
    assert result.data["sent"] is False
    assert "NOT been sent" in result.notice


async def test_email_draft_returns_the_composed_content():
    tool = EmailDraftTool()
    result = await tool.execute(
        {
            "recipient_name": "Jane Doe",
            "subject": "Interview invitation",
            "body": "We would like to speak with you.",
            "purpose": "interview_invite",
        }
    )
    draft = result.data["draft"]
    assert draft["to"] == "Jane Doe"
    assert draft["subject"] == "Interview invitation"
    assert draft["purpose"] == "interview_invite"


def test_email_tool_declares_itself_non_mutating():
    # Drafting changes nothing; the declaration should say so honestly.
    assert EmailDraftTool().is_mutating is False


# --- LinkedIn: mock only, never contacts LinkedIn ---

async def test_linkedin_returns_clearly_labelled_mock_data():
    result = await LinkedInProfileTool().execute(
        {"profile_url": "https://linkedin.com/in/janedoe"}
    )
    assert result.data["mock"] is True
    assert "mock" in result.data["headline"].lower()
    assert "Terms of Service" in result.notice


def test_linkedin_declares_no_external_effects():
    # It makes no real call, so claiming external effects would be
    # misleading in the opposite direction.
    assert LinkedInProfileTool().has_external_effects is False


def test_linkedin_description_states_it_does_not_contact_linkedin():
    # An LLM reading the tool list must not infer real lookup capability.
    description = LinkedInProfileTool().description.lower()
    assert "mock" in description
    assert "does not contact" in description or "not contact" in description


# --- GitHub: disabled by default ---

async def test_github_is_disabled_by_default():
    result = await GitHubProfileTool().execute({"username": "octocat"})
    assert result.success is False
    assert "disabled" in result.error.lower()


async def test_github_rejects_usernames_with_path_characters():
    # An unvalidated username interpolated into a URL could alter the path.
    tool = GitHubProfileTool(enabled=True)
    for bad in ["../../admin", "user/repo", "user?x=1", "user name"]:
        with pytest.raises(ToolError, match="Invalid GitHub username"):
            await tool.execute({"username": bad})


async def test_github_rejects_empty_username():
    with pytest.raises(ToolError):
        await GitHubProfileTool(enabled=True).execute({"username": "   "})


def test_github_declares_external_effects():
    assert GitHubProfileTool().has_external_effects is True


# --- Calendar: stub, books nothing ---

async def test_calendar_returns_weekday_slots_only():
    result = await CalendarAvailabilityTool().execute({"days_ahead": 14})
    from datetime import date

    for slot in result.data["suggested_slots"]:
        assert date.fromisoformat(slot["date"]).weekday() < 5


async def test_calendar_discloses_that_nothing_was_booked():
    result = await CalendarAvailabilityTool().execute({})
    assert "nothing was booked" in result.notice.lower()


async def test_calendar_respects_slots_per_day():
    result = await CalendarAvailabilityTool().execute({"days_ahead": 1, "slots_per_day": 2})
    slots = result.data["suggested_slots"]
    # One weekday at most in a 1-day window, so 0 or 2 slots.
    assert len(slots) in (0, 2)


# --- Filesystem: sandboxed, read-only ---

@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "storage"
    root.mkdir()
    (root / "notes.txt").write_text("candidate notes")
    (tmp_path / "secret.env").write_text("API_KEY=supersecret")
    return root


async def test_filesystem_reads_a_file_inside_the_sandbox(sandbox):
    result = await FilesystemReadTool(str(sandbox)).execute({"path": "notes.txt"})
    assert result.success is True
    assert result.data["content"] == "candidate notes"


async def test_filesystem_blocks_traversal_out_of_the_sandbox(sandbox):
    # The prompt-injection scenario: LLM output asks for a path outside.
    tool = FilesystemReadTool(str(sandbox))
    with pytest.raises(ToolError, match="escapes"):
        await tool.execute({"path": "../secret.env"})


async def test_filesystem_blocks_absolute_paths(sandbox):
    with pytest.raises(ToolError, match="Absolute"):
        await FilesystemReadTool(str(sandbox)).execute({"path": "/etc/passwd"})


async def test_filesystem_reports_missing_files_clearly(sandbox):
    with pytest.raises(ToolError, match="not found"):
        await FilesystemReadTool(str(sandbox)).execute({"path": "nope.txt"})


async def test_filesystem_rejects_directories(sandbox):
    (sandbox / "subdir").mkdir()
    with pytest.raises(ToolError, match="Not a file"):
        await FilesystemReadTool(str(sandbox)).execute({"path": "subdir"})


async def test_filesystem_refuses_oversized_files_rather_than_truncating(sandbox):
    # A silently truncated file could be summarized as though complete.
    big = sandbox / "big.txt"
    big.write_text("x" * (FilesystemReadTool.MAX_FILE_BYTES + 1))
    with pytest.raises(ToolError, match="exceeding"):
        await FilesystemReadTool(str(sandbox)).execute({"path": "big.txt"})


async def test_filesystem_rejects_non_utf8_files(sandbox):
    binary = sandbox / "image.bin"
    binary.write_bytes(b"\xff\xfe\x00\x01binary")
    with pytest.raises(ToolError, match="UTF-8"):
        await FilesystemReadTool(str(sandbox)).execute({"path": "image.bin"})


def test_filesystem_exposes_no_write_capability():
    # The tool surface itself should make writing impossible, not merely
    # discouraged.
    tool = FilesystemReadTool("/tmp")
    assert not hasattr(tool, "write")
    assert not hasattr(tool, "delete")
    assert "read-only" in tool.description.lower()
