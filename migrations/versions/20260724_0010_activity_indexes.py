"""Index the long-lived activity history.

Revision ID: 20260724_0010
Revises: 20260724_0009
Create Date: 2026-07-24
"""

from alembic import op

revision = "20260724_0010"
down_revision = "20260724_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Speed up timeline and user filters without rewriting activity data."""

    op.create_index(
        "ix_activities_occurred_at",
        "activities",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_activities_user_id",
        "activities",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Indexes remain in place because production migrations are append-only."""
