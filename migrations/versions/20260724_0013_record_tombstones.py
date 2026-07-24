"""Add append-only tombstones for non-destructive permanent UI deletion.

Revision ID: 20260724_0013
Revises: 20260724_0012
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0013"
down_revision = "20260724_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create a technical preservation layer without changing domain tables."""

    op.create_table(
        "record_tombstones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("module", sa.String(length=50), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column(
            "deleted_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            name="uq_record_tombstones_entity",
        ),
    )
    op.create_index(
        "ix_record_tombstones_entity_type",
        "record_tombstones",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_record_tombstones_entity_id",
        "record_tombstones",
        ["entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_record_tombstones_module",
        "record_tombstones",
        ["module"],
        unique=False,
    )
    op.create_index(
        "ix_record_tombstones_deleted_by_id",
        "record_tombstones",
        ["deleted_by_id"],
        unique=False,
    )
    op.create_index(
        "ix_record_tombstones_deleted_at",
        "record_tombstones",
        ["deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    """Keep deletion evidence because production migrations are append-only."""
