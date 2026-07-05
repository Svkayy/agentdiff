"""Audit log helper — records org-scoped actions for the dashboard audit trail."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from server.models import AuditLog


async def record_audit(
    session: AsyncSession,
    org_id: uuid.UUID,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    meta: dict | None = None,
) -> AuditLog:
    """Insert an AuditLog row. Does not commit — caller controls the transaction
    boundary so the audit row lands atomically with the action it records."""
    entry = AuditLog(
        org_id=org_id,
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        meta=meta,
    )
    session.add(entry)
    return entry
