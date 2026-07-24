"""Add persistent inspiration-table placements without changing moodboard items.

Revision ID: 20260724_0012
Revises: 20260724_0011
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0012"
down_revision = "20260724_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create an additive layout table; every existing moodboard item remains intact."""

    op.create_table(
        "moodboard_inspiration_placements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("moodboard_items.id"),
            nullable=False,
        ),
        sa.Column("x_percent", sa.Float(), nullable=False, server_default="5"),
        sa.Column("y_percent", sa.Float(), nullable=False, server_default="5"),
        sa.Column("rotation_degrees", sa.Float(), nullable=False, server_default="0"),
        sa.Column("layer", sa.Integer(), nullable=False, server_default="1"),
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
        sa.UniqueConstraint(
            "item_id",
            name="uq_moodboard_inspiration_placements_item_id",
        ),
    )
    op.create_index(
        "ix_moodboard_inspiration_placements_item_id",
        "moodboard_inspiration_placements",
        ["item_id"],
        unique=False,
    )


def downgrade() -> None:
    """Keep inspiration layouts because production migrations are append-only."""
