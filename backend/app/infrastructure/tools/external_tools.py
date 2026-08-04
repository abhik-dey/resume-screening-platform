"""
Tools reaching outside the system: GitHub, LinkedIn, calendar, email,
filesystem.

Each carries a deliberate constraint, documented at the tool rather than
buried in a config file, because the constraints are the design.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from app.domain.entities.user import UserRole
from app.domain.tools.base import Tool, ToolError, ToolResult
from app.domain.tools.path_sandbox import PathSandboxError, resolve_within

GITHUB_API_BASE = "https://api.github.com"
GITHUB_TIMEOUT_SECONDS = 10.0


class GitHubProfileTool(Tool):
    """Fetch a public GitHub profile.

    DISABLED BY DEFAULT. Makes real outbound requests, and the username can
    originate from LLM output influenced by resume content — so it's opt-in
    via config rather than silently reachable.
    """

    name = "github_profile"
    description = (
        "Fetch a public GitHub profile: name, bio, public repo count, followers. "
        "Requires GITHUB_TOOL_ENABLED=true."
    )
    required_role = UserRole.RECRUITER
    has_external_effects = True

    def __init__(self, enabled: bool = False, token: str = "") -> None:
        self._enabled = enabled
        self._token = token

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "maxLength": 39,  # GitHub's own limit
                    "description": "GitHub username",
                }
            },
            "required": ["username"],
        }

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        if not self._enabled:
            return ToolResult(
                success=False,
                error="The GitHub tool is disabled. Set GITHUB_TOOL_ENABLED=true to enable it.",
                notice="Disabled by default because it makes real outbound network requests.",
            )

        username = params["username"].strip()
        # Validate before interpolating into a URL. GitHub usernames are
        # alphanumeric plus hyphens; anything else could alter the path.
        if not username or not all(c.isalnum() or c == "-" for c in username):
            raise ToolError(
                f"Invalid GitHub username: '{username}'. Only letters, digits, and hyphens."
            )

        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            async with httpx.AsyncClient(timeout=GITHUB_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{GITHUB_API_BASE}/users/{username}", headers=headers)
        except httpx.HTTPError as exc:
            raise ToolError(f"GitHub request failed: {exc}") from exc

        if response.status_code == 404:
            return ToolResult(success=True, data={"found": False, "username": username})
        if response.status_code == 403:
            raise ToolError("GitHub rate limit exceeded. Set GITHUB_TOKEN to raise the limit.")
        if response.status_code != 200:
            raise ToolError(f"GitHub returned {response.status_code}")

        body = response.json()
        return ToolResult(
            success=True,
            data={
                "found": True,
                "username": body.get("login"),
                "name": body.get("name"),
                "bio": body.get("bio"),
                "public_repos": body.get("public_repos"),
                "followers": body.get("followers"),
                "profile_url": body.get("html_url"),
            },
        )


class LinkedInProfileTool(Tool):
    """MOCK ONLY — returns synthetic data, never contacts LinkedIn.

    This is not a placeholder awaiting a real implementation. Scraping
    LinkedIn violates their Terms of Service, and their official API does
    not offer arbitrary profile lookup. The original spec said "mock", and
    that's the correct and permanent answer here.
    """

    name = "linkedin_profile"
    description = (
        "MOCK: returns synthetic LinkedIn profile data for development. Does NOT contact "
        "LinkedIn — scraping violates their Terms of Service and no API offers this lookup."
    )
    required_role = UserRole.RECRUITER
    has_external_effects = False  # deliberately false: it makes no real call

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"profile_url": {"type": "string", "maxLength": 500}},
            "required": ["profile_url"],
        }

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True,
            data={
                "mock": True,
                "profile_url": params["profile_url"],
                "headline": "[mock data — not retrieved from LinkedIn]",
                "current_position": "[mock data]",
                "connections": "[mock data]",
            },
            notice=(
                "This is synthetic data. LinkedIn is never contacted: scraping violates their "
                "Terms of Service, and no official API provides arbitrary profile lookup. Do not "
                "present this as real candidate information."
            ),
        )


class CalendarAvailabilityTool(Tool):
    """In-memory availability stub.

    No calendar system is integrated, so this generates plausible weekday
    slots rather than pretending to read a real calendar. Clearly labelled
    so its output is never mistaken for actual availability.
    """

    name = "calendar_availability"
    description = (
        "STUB: suggests interview slots on upcoming weekdays. Not connected to any real "
        "calendar — does not check actual availability or book anything."
    )
    required_role = UserRole.RECRUITER

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "minimum": 1, "maximum": 30},
                "slots_per_day": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            "required": [],
        }

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        days_ahead = params.get("days_ahead", 7)
        slots_per_day = params.get("slots_per_day", 3)
        start_hours = [9, 11, 14, 16, 10, 13, 15, 17][:slots_per_day]

        today = datetime.now(timezone.utc).date()
        slots = []
        for offset in range(1, days_ahead + 1):
            day = today + timedelta(days=offset)
            if day.weekday() >= 5:  # skip weekends
                continue
            for hour in sorted(start_hours):
                slots.append({"date": day.isoformat(), "time": f"{hour:02d}:00 UTC"})

        return ToolResult(
            success=True,
            data={"suggested_slots": slots},
            notice=(
                "Suggested slots only. No calendar was checked and nothing was booked — "
                "confirm real availability before offering these to a candidate."
            ),
        )


class EmailDraftTool(Tool):
    """Compose an email draft. NEVER SENDS.

    An LLM with send capability can email a candidate a rejection by
    mistake, and that is not recoverable. Drafting keeps a human in the
    loop for an irreversible, externally-visible action. This is a
    deliberate design limit, not a missing feature.
    """

    name = "email_draft"
    description = (
        "Compose an email draft for a recruiter to review and send manually. "
        "This tool NEVER sends email."
    )
    required_role = UserRole.RECRUITER
    is_mutating = False  # drafting changes nothing

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "recipient_name": {"type": "string", "maxLength": 200},
                "subject": {"type": "string", "maxLength": 300},
                "body": {"type": "string", "maxLength": 5000},
                "purpose": {
                    "type": "string",
                    "enum": ["interview_invite", "follow_up", "rejection", "offer", "other"],
                },
            },
            "required": ["recipient_name", "subject", "body"],
        }

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True,
            data={
                "draft": {
                    "to": params["recipient_name"],
                    "subject": params["subject"],
                    "body": params["body"],
                    "purpose": params.get("purpose", "other"),
                },
                "sent": False,
            },
            notice=(
                "DRAFT ONLY — this email has NOT been sent. Review it and send it yourself. "
                "Automated sending is deliberately not supported: an incorrectly sent message "
                "to a candidate cannot be recalled."
            ),
        )


class FilesystemReadTool(Tool):
    """Read a text file from a sandboxed directory. READ-ONLY.

    Tool parameters can originate from LLM output influenced by resume
    content, which is attacker-controlled — so an unconstrained filesystem
    tool is a prompt-injection path straight to .env or /etc/passwd.

    Constraints: reads only, inside one allowlisted root, with paths
    resolved before containment checking (see domain/tools/path_sandbox.py).
    No write, no delete, no directory listing outside the root.
    """

    name = "filesystem_read"
    description = (
        "Read a UTF-8 text file from the sandboxed storage directory. Read-only; paths "
        "outside the sandbox are rejected."
    )
    required_role = UserRole.RECRUITER
    has_external_effects = True

    # Refusing rather than truncating: a silently truncated file could be
    # summarized as though it were complete.
    MAX_FILE_BYTES = 512 * 1024

    def __init__(self, sandbox_root: str) -> None:
        self._root = Path(sandbox_root)

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "maxLength": 500,
                    "description": "Path relative to the sandbox root. Absolute paths and "
                    "parent traversal are rejected.",
                }
            },
            "required": ["path"],
        }

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        try:
            resolved = resolve_within(self._root, params["path"])
        except PathSandboxError as exc:
            raise ToolError(str(exc)) from exc

        if not resolved.exists():
            raise ToolError(f"File not found: {params['path']}")
        if not resolved.is_file():
            raise ToolError(f"Not a file: {params['path']}")

        size = resolved.stat().st_size
        if size > self.MAX_FILE_BYTES:
            raise ToolError(
                f"File is {size} bytes, exceeding the {self.MAX_FILE_BYTES}-byte limit"
            )

        try:
            content = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ToolError(f"File is not valid UTF-8 text: {params['path']}") from exc

        return ToolResult(
            success=True,
            data={"path": params["path"], "size_bytes": size, "content": content},
        )
