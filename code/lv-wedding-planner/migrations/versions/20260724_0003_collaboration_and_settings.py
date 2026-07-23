"""Add collaboration audit fields, communication storage and project settings.

Revision ID: 20260724_0003
Revises: 20260724_0002
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0003"
down_revision = "20260724_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = (
        "activities",
        "vendors",
        "budget_categories",
        "expenses",
        "guests",
        "tasks",
        "legal_documents",
        "workspace_records",
    )
    for table in tables:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("created_by_id", sa.Integer(), nullable=True))
            batch.add_column(sa.Column("updated_by_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("activities") as batch:
        batch.add_column(
            sa.Column("module", sa.String(50), nullable=False, server_default="system")
        )
    op.create_index("ix_activities_module", "activities", ["module"])
    with op.batch_alter_table("workspace_records") as batch:
        batch.add_column(
            sa.Column("attachment_path", sa.String(500), nullable=False, server_default="")
        )
    op.create_table(
        "project_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "project_name", sa.String(150), nullable=False, server_default="LV – Wedding Planner"
        ),
        sa.Column("primary_color", sa.String(20), nullable=False, server_default="#D88BA7"),
        sa.Column("secondary_color", sa.String(20), nullable=False, server_default="#F8DCE8"),
        sa.Column("logo_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("wedding_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_budget", sa.String(50), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(10), nullable=False, server_default="EUR"),
        sa.Column("language", sa.String(10), nullable=False, server_default="pt-PT"),
    )


def downgrade() -> None:
    """Schema remains append-only to preserve user data."""
