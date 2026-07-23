from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampedModel


class Vendor(TimestampedModel, Base):
    __tablename__ = "vendors"

    vendor_type: Mapped[str] = mapped_column(String(100), index=True)
    company: Mapped[str] = mapped_column(String(200), index=True)
    contact_name: Mapped[str] = mapped_column(String(150), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    website: Mapped[str] = mapped_column(String(300), default="")
    agreed_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    deposit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    final_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_path: Mapped[str] = mapped_column(String(500), default="")
    invoice_path: Mapped[str] = mapped_column(String(500), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class BudgetCategory(TimestampedModel, Base):
    __tablename__ = "budget_categories"

    name: Mapped[str] = mapped_column(String(100), unique=True)
    planned_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Expense(TimestampedModel, Base):
    __tablename__ = "expenses"

    category_id: Mapped[int] = mapped_column(ForeignKey("budget_categories.id"), index=True)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), nullable=True)
    description: Mapped[str] = mapped_column(String(250))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    expense_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="Pendente")
    receipt_path: Mapped[str] = mapped_column(String(500), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Guest(TimestampedModel, Base):
    __tablename__ = "guests"

    name: Mapped[str] = mapped_column(String(200), index=True)
    congregation: Mapped[str] = mapped_column(String(150), default="", index=True)
    sex: Mapped[str] = mapped_column(String(20), default="")
    side: Mapped[str] = mapped_column(String(30), default="")
    age_group: Mapped[str] = mapped_column(String(30), default="Adulto")
    rsvp_status: Mapped[str] = mapped_column(String(30), default="Pendente", index=True)
    table_name: Mapped[str] = mapped_column(String(100), default="")
    dietary_requirements: Mapped[str] = mapped_column(Text, default="")
    special_needs: Mapped[str] = mapped_column(Text, default="")
    address: Mapped[str] = mapped_column(Text, default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    invitation_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    gift_received: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Task(TimestampedModel, Base):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(250), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    priority: Mapped[str] = mapped_column(String(30), default="Média")
    assignee: Mapped[str] = mapped_column(String(100), default="")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="Pendente", index=True)
    tags: Mapped[str] = mapped_column(String(250), default="")
    comments: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class LegalDocument(TimestampedModel, Base):
    __tablename__ = "legal_documents"

    document_type: Mapped[str] = mapped_column(String(100), default="Documento")
    title: Mapped[str] = mapped_column(String(200), index=True)
    status: Mapped[str] = mapped_column(String(30), default="Pendente")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsible: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
