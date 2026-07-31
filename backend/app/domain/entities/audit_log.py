"""
AuditLog domain entity.

Deliberately has NO foreign keys to other entities — see the design note in
app/infrastructure/db/models/audit_log.py for why. `input_ref` is a plain
string like "resume:<uuid>" rather than a relationship.
"""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class AuditLog:
    id: UUID
    agent_name: str
    input_ref: str
    output: dict | None = None
    reasoning: str | None = None
    model_used: str | None = None
    created_at: datetime | None = None
