"""Abstract repository interface for AuditLog persistence."""
from abc import ABC, abstractmethod

from app.domain.entities.audit_log import AuditLog


class AuditLogRepository(ABC):
    @abstractmethod
    async def create(self, audit_log: AuditLog) -> AuditLog:
        """Persist a new audit log entry and return the stored representation."""
