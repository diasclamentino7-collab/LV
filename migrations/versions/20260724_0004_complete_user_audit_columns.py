"""Complete audit columns for existing users table.

Revision ID: 20260724_0004
Revises: 20260724_0003
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0004"
down_revision = "20260724_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable audit references without modifying existing user records."""
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("created_by_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("updated_by_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Schema remains append-only to preserve production data."""
