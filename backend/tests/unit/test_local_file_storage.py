from pathlib import Path

import pytest

from app.infrastructure.storage.local_file_storage import LocalFileStorage


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(base_dir=str(tmp_path / "resumes"))


async def test_save_creates_a_file_with_generated_name(storage: LocalFileStorage):
    storage_path = await storage.save(b"hello world", "original_name.pdf")
    assert storage_path.endswith(".pdf")
    assert storage_path != "original_name.pdf"  # never trusts the original name


async def test_save_then_read_roundtrip(storage: LocalFileStorage):
    content = b"some resume bytes"
    storage_path = await storage.save(content, "resume.pdf")
    read_back = await storage.read(storage_path)
    assert read_back == content


async def test_delete_removes_the_file(storage: LocalFileStorage):
    storage_path = await storage.save(b"content", "resume.docx")
    await storage.delete(storage_path)
    with pytest.raises(FileNotFoundError):
        await storage.read(storage_path)


async def test_delete_is_idempotent_for_missing_file(storage: LocalFileStorage):
    # Deleting something that was never saved (or already deleted) must not raise.
    await storage.delete("nonexistent-file.pdf")


async def test_resolve_rejects_path_traversal(storage: LocalFileStorage):
    with pytest.raises(ValueError):
        await storage.read("../../../etc/passwd")
