"""Add persistent moodboard boards, collections and items.

Revision ID: 20260724_0007
Revises: 20260724_0006
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0007"
down_revision = "20260724_0006"
branch_labels = None
depends_on = None


def audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "moodboard_boards",
        *audit_columns(),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "moodboard_collections",
        *audit_columns(),
        sa.Column("board_id", sa.Integer(), sa.ForeignKey("moodboard_boards.id"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "moodboard_items",
        *audit_columns(),
        sa.Column(
            "collection_id", sa.Integer(), sa.ForeignKey("moodboard_collections.id"), nullable=False
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(1000), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False, server_default=""),
        sa.Column("tags", sa.String(300), nullable=False, server_default=""),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_moodboard_items_title", "moodboard_items", ["title"])


def downgrade() -> None:
    """Schema remains append-only to preserve production data."""
