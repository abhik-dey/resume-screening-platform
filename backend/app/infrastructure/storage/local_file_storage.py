"""
Local filesystem implementation of FileStorage.

Generates its own random, collision-free on-disk filename rather than
trusting the caller's original filename — this is a deliberate security
choice: user-supplied filenames must never be used to construct a
filesystem path (classic path-traversal risk, e.g. "../../etc/passwd").
The human-readable original filename is stored separately in the database
(Resume.original_filename), purely for display purposes.
"""
import uuid
from pathlib import Path

import aiofiles
import aiofiles.os

from app.domain.interfaces.file_storage import FileStorage


class LocalFileStorage(FileStorage):
    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, content: bytes, filename: str) -> str:
        extension = Path(filename).suffix.lower()
        safe_name = f"{uuid.uuid4()}{extension}"
        full_path = self._base_dir / safe_name

        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)

        # Return a path relative to base_dir — keeps the stored value
        # portable if base_dir ever moves (e.g. a different mount point).
        return safe_name

    async def read(self, storage_path: str) -> bytes:
        full_path = self._resolve(storage_path)
        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def delete(self, storage_path: str) -> None:
        full_path = self._resolve(storage_path)
        try:
            await aiofiles.os.remove(full_path)
        except FileNotFoundError:
            pass  # Already gone — deleting an absent file is not an error here.

    def _resolve(self, storage_path: str) -> Path:
        full_path = (self._base_dir / storage_path).resolve()
        # Defense in depth: even though save() generates safe_name itself,
        # reject any storage_path that would resolve outside base_dir.
        if self._base_dir.resolve() not in full_path.parents and full_path != self._base_dir.resolve():
            raise ValueError(f"Invalid storage path: {storage_path}")
        return full_path
