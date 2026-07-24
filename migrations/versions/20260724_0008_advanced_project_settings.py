"""Add advanced project planning settings.

Revision ID: 20260724_0008
Revises: 20260724_0007
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0008"
down_revision = "20260724_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add settings without rewriting or removing existing project data."""
    with op.batch_alter_table("project_settings") as batch:
        batch.add_column(
            sa.Column("partner_one_name", sa.String(100), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("partner_two_name", sa.String(100), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column(
                "wedding_style",
                sa.String(50),
                nullable=False,
                server_default="Mid-century vintage",
            )
        )
        batch.add_column(
            sa.Column(
                "wedding_timezone",
                sa.String(64),
                nullable=False,
                server_default="Europe/Lisbon",
            )
        )
        batch.add_column(
            sa.Column("wedding_city", sa.String(150), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("ceremony_venue", sa.String(200), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("reception_venue", sa.String(200), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("guest_target", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("budget_alert_percent", sa.Integer(), nullable=False, server_default="80")
        )
        batch.add_column(
            sa.Column(
                "accent_color",
                sa.String(20),
                nullable=False,
                server_default="#C9A46A",
            )
        )
        batch.add_column(
            sa.Column(
                "background_color",
                sa.String(20),
                nullable=False,
                server_default="#FAF8F6",
            )
        )
        batch.add_column(
            sa.Column("reminder_days_before", sa.Integer(), nullable=False, server_default="7")
        )
        batch.add_column(
            sa.Column(
                "reminders_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch.add_column(
            sa.Column("default_assignee", sa.String(100), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column(
                "default_task_priority",
                sa.String(30),
                nullable=False,
                server_default="Média",
            )
        )
        batch.add_column(
            sa.Column(
                "dashboard_show_countdown",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch.add_column(
            sa.Column(
                "dashboard_show_finance",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch.add_column(
            sa.Column(
                "dashboard_show_activity",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch.add_column(
            sa.Column(
                "dashboard_show_moodboard",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch.add_column(
            sa.Column("settings_version", sa.Integer(), nullable=False, server_default="1")
        )


def downgrade() -> None:
    """Schema remains append-only to preserve production data."""
