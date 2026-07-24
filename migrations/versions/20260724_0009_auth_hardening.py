"""Add session revocation and persistent login protection.

Revision ID: 20260724_0009
Revises: 20260724_0008
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0009"
down_revision = "20260724_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add authentication safeguards without changing existing accounts."""

    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "session_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch.add_column(
            sa.Column(
                "failed_login_attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    """Schema remains append-only so authentication history is preserved."""
