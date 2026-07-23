"""Initial empty baseline.

Revision ID: 20260723_0001
Revises:
Create Date: 2026-07-23

This establishes Alembic version tracking before domain tables are introduced.
"""

# revision identifiers, used by Alembic.
revision = "20260723_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No domain tables exist in the initial scaffold."""


def downgrade() -> None:
    """No domain tables exist in the initial scaffold."""
