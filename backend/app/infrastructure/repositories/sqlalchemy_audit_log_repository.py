"""Concrete AuditLogRepository backed by SQLAlchemy's async ORM."""
from app.domain.entities.audit_log import AuditLog
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.infrastructure.db.models.audit_log import AuditLogModel


class SQLAlchemyAuditLogRepository(AuditLogRepository):
    def __init__(self, session) -> None:
        self._session = session

    async def create(self, audit_log: AuditLog) -> AuditLog:
        model = AuditLogModel(
            id=audit_log.id,
            agent_name=audit_log.agent_name,
            input_ref=audit_log.input_ref,
            output=audit_log.output,
            reasoning=audit_log.reasoning,
            model_used=audit_log.model_used,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return AuditLog(
            id=model.id,
            agent_name=model.agent_name,
            input_ref=model.input_ref,
            output=model.output,
            reasoning=model.reasoning,
            model_used=model.model_used,
            created_at=model.created_at,
        )
