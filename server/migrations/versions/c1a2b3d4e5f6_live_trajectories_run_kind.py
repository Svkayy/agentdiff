"""live trajectories + run kind

Revision ID: c1a2b3d4e5f6
Revises: b34c322917a3
Create Date: 2026-07-03 13:28:08.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c1a2b3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "b34c322917a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add kind column to runs and create live_trajectories table."""
    # Add 'kind' column to runs (default 'ci', server_default 'ci')
    op.add_column(
        "runs",
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            server_default="ci",
        ),
    )

    # Create live_trajectories table
    op.create_table(
        "live_trajectories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_live_trajectories_project_id",
        "live_trajectories",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_live_trajectories_captured_at",
        "live_trajectories",
        ["captured_at"],
        unique=False,
    )


def downgrade() -> None:
    """Reverse migration."""
    op.drop_index("ix_live_trajectories_captured_at", table_name="live_trajectories")
    op.drop_index("ix_live_trajectories_project_id", table_name="live_trajectories")
    op.drop_table("live_trajectories")
    op.drop_column("runs", "kind")
