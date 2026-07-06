"""slack webhook url

Revision ID: d2e3f4a5b6c7
Revises: c1a2b3d4e5f6
Create Date: 2026-07-03 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1a2b3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add webhook_url_encrypted column to slack_configs (nullable — safe)."""
    op.add_column(
        "slack_configs",
        sa.Column("webhook_url_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Reverse migration."""
    op.drop_column("slack_configs", "webhook_url_encrypted")
