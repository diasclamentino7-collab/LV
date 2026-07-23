"""Add persistent authentication and planning modules.

Revision ID: 20260724_0002
Revises: 20260723_0001
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0002"
down_revision = "20260723_0001"
branch_labels = None
depends_on = None


def audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        *audit_columns(),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_users_name", "users", ["name"])
    op.create_table(
        "activities",
        *audit_columns(),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_activities_action_type", "activities", ["action_type"])
    op.create_table(
        "vendors",
        *audit_columns(),
        sa.Column("vendor_type", sa.String(100), nullable=False),
        sa.Column("company", sa.String(200), nullable=False),
        sa.Column("contact_name", sa.String(150), nullable=False, server_default=""),
        sa.Column("phone", sa.String(50), nullable=False, server_default=""),
        sa.Column("email", sa.String(200), nullable=False, server_default=""),
        sa.Column("website", sa.String(300), nullable=False, server_default=""),
        sa.Column("agreed_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("paid_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("deposit_date", sa.Date(), nullable=True),
        sa.Column("final_payment_date", sa.Date(), nullable=True),
        sa.Column("contract_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("invoice_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_vendors_company", "vendors", ["company"])
    op.create_index("ix_vendors_vendor_type", "vendors", ["vendor_type"])
    op.create_table(
        "budget_categories",
        *audit_columns(),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("planned_limit", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "expenses",
        *audit_columns(),
        sa.Column(
            "category_id", sa.Integer(), sa.ForeignKey("budget_categories.id"), nullable=False
        ),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id"), nullable=True),
        sa.Column("description", sa.String(250), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="Pendente"),
        sa.Column("receipt_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_expenses_category_id", "expenses", ["category_id"])
    op.create_table(
        "guests",
        *audit_columns(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("congregation", sa.String(150), nullable=False, server_default=""),
        sa.Column("sex", sa.String(20), nullable=False, server_default=""),
        sa.Column("side", sa.String(30), nullable=False, server_default=""),
        sa.Column("age_group", sa.String(30), nullable=False, server_default="Adulto"),
        sa.Column("rsvp_status", sa.String(30), nullable=False, server_default="Pendente"),
        sa.Column("table_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("dietary_requirements", sa.Text(), nullable=False, server_default=""),
        sa.Column("special_needs", sa.Text(), nullable=False, server_default=""),
        sa.Column("address", sa.Text(), nullable=False, server_default=""),
        sa.Column("phone", sa.String(50), nullable=False, server_default=""),
        sa.Column("email", sa.String(200), nullable=False, server_default=""),
        sa.Column("invitation_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("gift_received", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_guests_name", "guests", ["name"])
    op.create_table(
        "tasks",
        *audit_columns(),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(100), nullable=False, server_default=""),
        sa.Column("priority", sa.String(30), nullable=False, server_default="Média"),
        sa.Column("assignee", sa.String(100), nullable=False, server_default=""),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="Pendente"),
        sa.Column("tags", sa.String(250), nullable=False, server_default=""),
        sa.Column("comments", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_tasks_title", "tasks", ["title"])
    op.create_table(
        "legal_documents",
        *audit_columns(),
        sa.Column("document_type", sa.String(100), nullable=False, server_default="Documento"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="Pendente"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("responsible", sa.String(100), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_legal_documents_title", "legal_documents", ["title"])
    op.create_table(
        "workspace_records",
        *audit_columns(),
        sa.Column("module", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(50), nullable=False, server_default="Pendente"),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_workspace_records_module", "workspace_records", ["module"])
    op.create_index("ix_workspace_records_title", "workspace_records", ["title"])


def downgrade() -> None:
    """Schema is intentionally append-only; production data is never dropped."""
