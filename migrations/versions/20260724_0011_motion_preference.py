"""Add the shared motion preference.

Revision ID: 20260724_0011
Revises: 20260724_0010
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0011"
down_revision = "20260724_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add motion configuration without rewriting existing project settings."""

    op.add_column(
        "project_settings",
        sa.Column(
            "motion_preference",
            sa.String(20),
            nullable=False,
            server_default="full",
        ),
    )


def downgrade() -> None:
    """The preference remains stored because production migrations are append-only."""
