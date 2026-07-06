"""audit_logs.project_id: dedicated column for project-scoped audit queries

Revision ID: e8c548d962b1
Revises: 0c7fdcec7587
Create Date: 2026-07-05 19:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8c548d962b1"
down_revision: Union[str, Sequence[str], None] = "0c7fdcec7587"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable audit_logs.project_id + composite index.

    Plain nullable column (not a hard FK-cascade): audit rows must survive
    deletion of the project they reference, so a deleted project's audit
    trail is retained rather than being cascade-deleted or left dangling
    under an FK constraint.
    """
    op.add_column("audit_logs", sa.Column("project_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_audit_logs_project_id_created_at",
        "audit_logs",
        ["project_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_audit_logs_project_id_created_at", table_name="audit_logs")
    op.drop_column("audit_logs", "project_id")
