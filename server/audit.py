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
    project_id: uuid.UUID | None = None,
) -> AuditLog:
    """Insert an AuditLog row. Does not commit — caller controls the transaction
    boundary so the audit row lands atomically with the action it records.

    `project_id` is a dedicated, indexed column used for project-scoped audit
    queries (see server/routes/manage.py::list_audit). It is independent of
    `meta`, which callers may still populate for backward compatibility with
    existing rows/consumers that read meta['project_id']."""
    entry = AuditLog(
        org_id=org_id,
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        meta=meta,
        project_id=project_id,
    )
    session.add(entry)
    return entry
