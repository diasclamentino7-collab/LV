"""Add reusable detail fields for communication and venue records.

Revision ID: 20260724_0005
Revises: 20260724_0004
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0005"
down_revision = "20260724_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workspace_records") as batch:
        batch.add_column(sa.Column("category", sa.String(100), nullable=False, server_default=""))
        batch.add_column(
            sa.Column("responsible", sa.String(100), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("priority", sa.String(30), nullable=False, server_default="Média")
        )
        batch.add_column(sa.Column("comments", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("location", sa.String(200), nullable=False, server_default=""))
        batch.add_column(sa.Column("contact", sa.String(200), nullable=False, server_default=""))
        batch.add_column(sa.Column("source_url", sa.String(500), nullable=False, server_default=""))


def downgrade() -> None:
    """Schema remains append-only to preserve production data."""
