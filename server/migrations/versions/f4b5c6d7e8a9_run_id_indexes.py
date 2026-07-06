"""Indexes for trajectories.run_id / findings.run_id FKs and runs.created_at.

Postgres does not auto-index foreign keys: run-detail reads, notification
enrichment GROUP BYs, and retention deletes were seq-scanning the two largest
(JSONB-heavy) tables. runs.created_at serves the retention cutoff scan.

Revision ID: f4b5c6d7e8a9
Revises: e8c548d962b1
Create Date: 2026-07-06
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f4b5c6d7e8a9"
down_revision: Union[str, Sequence[str], None] = "e8c548d962b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_trajectories_run_id", "trajectories", ["run_id"])
    op.create_index("ix_findings_run_id", "findings", ["run_id"])
    op.create_index("ix_runs_created_at", "runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_runs_created_at", table_name="runs")
    op.drop_index("ix_findings_run_id", table_name="findings")
    op.drop_index("ix_trajectories_run_id", table_name="trajectories")
