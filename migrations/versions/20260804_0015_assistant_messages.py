"""Add the AI assistant conversation table.

Revision ID: 20260804_0015
Revises: 20260724_0014
Create Date: 2026-08-04
"""

import sqlalchemy as sa
from alembic import op

revision = "20260804_0015"
down_revision = "20260724_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create a new, additive table; no existing data is touched."""

    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index(
        "ix_assistant_messages_provider",
        "assistant_messages",
        ["provider"],
        unique=False,
    )


def downgrade() -> None:
    """Keep assistant conversations because production migrations are append-only."""
