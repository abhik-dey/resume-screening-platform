"""
Abstract file storage interface.

Same adapter pattern as the LLM provider interface from Phase 1: business
logic depends on this abstraction, never on `open()`/`boto3`/etc directly.
Today's implementation is local disk (LocalFileStorage); the original
project spec calls for migrating to S3-compatible storage later — that
migration means writing one new adapter class, not touching ResumeUploadService.
"""
from abc import ABC, abstractmethod


class FileStorage(ABC):
    @abstractmethod
    async def save(self, content: bytes, filename: str) -> str:
        """Persist `content` and return a storage_path/key that can later be
        passed to `read()` or `delete()`. Implementations must generate their
        own safe on-disk/object-key name — never trust `filename` directly."""

    @abstractmethod
    async def read(self, storage_path: str) -> bytes:
        """Return the raw bytes previously saved at `storage_path`."""

    @abstractmethod
    async def delete(self, storage_path: str) -> None:
        """Remove the file at `storage_path`. Should not raise if already absent."""
