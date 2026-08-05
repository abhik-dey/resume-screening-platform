"""
Base class for all agents in the pipeline.

Every agent extends this and implements `_execute()`. `run()` provides the
cross-cutting concerns every agent needs: audit logging (Phase 1's
traceability requirement) and a consistent success/failure result shape,
so failures never propagate as unhandled exceptions past the API layer.
"""
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.observability.logging_config import get_logger
from app.core.observability.metrics import record_agent_run
from app.core.observability.tracing import span
from app.domain.entities.audit_log import AuditLog
from app.domain.interfaces.audit_log_repository import AuditLogRepository

logger = get_logger(__name__)


@dataclass
class AgentResult:
    success: bool
    output: dict[str, Any] | None
    reasoning: str


class BaseAgent(ABC):
    agent_name: str

    def __init__(self, audit_log_repository: AuditLogRepository, model_name: str) -> None:
        self._audit_logs = audit_log_repository
        self._model_name = model_name

    async def run(self, input_ref: str, **kwargs: Any) -> AgentResult:
        # Instrumented HERE rather than in each agent: run() is the single
        # choke point every agent passes through, so metrics, tracing, and
        # logging can't be forgotten when a new agent is added.
        started = time.perf_counter()
        with span(f"agent.{self.agent_name}", agent=self.agent_name, input_ref=input_ref):
            try:
                output, reasoning = await self._execute(**kwargs)
                await self._record_audit(input_ref, output, reasoning)
                duration = time.perf_counter() - started
                record_agent_run(self.agent_name, success=True, duration_seconds=duration)
                logger.info(
                    "agent completed",
                    extra={
                        "agent": self.agent_name,
                        "input_ref": input_ref,
                        "success": True,
                        "duration_ms": round(duration * 1000, 2),
                    },
                )
                return AgentResult(success=True, output=output, reasoning=reasoning)
            except Exception as exc:  # noqa: BLE001 -- any agent failure must be captured, not crash the API
                reasoning = f"{type(exc).__name__}: {exc}"
                await self._record_audit(input_ref, None, reasoning)
                duration = time.perf_counter() - started
                record_agent_run(self.agent_name, success=False, duration_seconds=duration)
                logger.warning(
                    "agent failed",
                    extra={
                        "agent": self.agent_name,
                        "input_ref": input_ref,
                        "success": False,
                        "duration_ms": round(duration * 1000, 2),
                        "error_type": type(exc).__name__,
                    },
                )
                return AgentResult(success=False, output=None, reasoning=reasoning)

    @abstractmethod
    async def _execute(self, **kwargs: Any) -> tuple[dict[str, Any], str]:
        """Do the agent's actual work. Return (output_dict, human_readable_reasoning).
        Any exception raised here is caught by `run()`, audit-logged, and
        turned into a failed AgentResult."""

    async def _record_audit(self, input_ref: str, output: dict[str, Any] | None, reasoning: str) -> None:
        await self._audit_logs.create(
            AuditLog(
                id=uuid4(),
                agent_name=self.agent_name,
                input_ref=input_ref,
                output=output,
                reasoning=reasoning,
                model_used=self._model_name,
                created_at=datetime.now(timezone.utc),
            )
        )
