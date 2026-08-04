"""
Path sandbox tests.

Exhaustive on traversal payloads: this is the control preventing a
prompt-injected filesystem read, and a gap here is a critical
vulnerability rather than a bug.
"""
from pathlib import Path

import pytest

from app.domain.tools.path_sandbox import PathSandboxError, resolve_within


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    (root / "allowed.txt").write_text("safe content")
    (root / "subdir").mkdir()
    (root / "subdir" / "nested.txt").write_text("nested content")
    # A secret OUTSIDE the sandbox, standing in for .env or /etc/passwd.
    (tmp_path / "secret.txt").write_text("SECRET")
    return root


def test_simple_relative_path_resolves(sandbox):
    resolved = resolve_within(sandbox, "allowed.txt")
    assert resolved.read_text() == "safe content"


def test_nested_path_resolves(sandbox):
    resolved = resolve_within(sandbox, "subdir/nested.txt")
    assert resolved.read_text() == "nested content"


def test_dot_slash_prefix_is_fine(sandbox):
    assert resolve_within(sandbox, "./allowed.txt").read_text() == "safe content"


def test_parent_traversal_is_blocked(sandbox):
    with pytest.raises(PathSandboxError, match="escapes"):
        resolve_within(sandbox, "../secret.txt")


def test_deep_parent_traversal_is_blocked(sandbox):
    with pytest.raises(PathSandboxError):
        resolve_within(sandbox, "../../../../../../etc/passwd")


def test_traversal_hidden_mid_path_is_blocked(sandbox):
    # Looks like it stays inside until you resolve it.
    with pytest.raises(PathSandboxError):
        resolve_within(sandbox, "subdir/../../secret.txt")


def test_absolute_path_is_blocked(sandbox):
    with pytest.raises(PathSandboxError, match="Absolute"):
        resolve_within(sandbox, "/etc/passwd")


def test_null_byte_is_blocked(sandbox):
    # Null bytes can truncate paths in some underlying calls.
    with pytest.raises(PathSandboxError, match="null byte"):
        resolve_within(sandbox, "allowed.txt\x00.png")


def test_symlink_escaping_the_root_is_blocked(sandbox, tmp_path):
    # The case that string-matching for ".." would miss entirely.
    link = sandbox / "escape_link"
    link.symlink_to(tmp_path / "secret.txt")
    with pytest.raises(PathSandboxError, match="escapes"):
        resolve_within(sandbox, "escape_link")


def test_symlink_staying_inside_the_root_is_allowed(sandbox):
    link = sandbox / "inside_link"
    link.symlink_to(sandbox / "allowed.txt")
    assert resolve_within(sandbox, "inside_link").read_text() == "safe content"


def test_nonexistent_path_inside_root_resolves(sandbox):
    # "Not found" is the tool's error to report, not the sandbox's.
    resolved = resolve_within(sandbox, "does_not_exist.txt")
    assert not resolved.exists()


def test_sibling_directory_with_shared_prefix_is_blocked(tmp_path):
    # /tmp/x/sandbox vs /tmp/x/sandbox_evil — a naive startswith() check on
    # the path string would wrongly allow the second.
    root = tmp_path / "sandbox"
    root.mkdir()
    evil = tmp_path / "sandbox_evil"
    evil.mkdir()
    (evil / "secret.txt").write_text("SECRET")

    with pytest.raises(PathSandboxError):
        resolve_within(root, "../sandbox_evil/secret.txt")
