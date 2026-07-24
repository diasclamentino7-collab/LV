"""Dependency-free, paginated PDF reports for persisted planning data.

The writer intentionally uses the PDF 1.4 primitives supported by every modern
browser and PDF reader.  Keeping it in pure Python avoids fragile native
rendering dependencies in the free Render deployment.
"""

from __future__ import annotations

import json
import re
import textwrap
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import RecordTombstone, User
from app.models.moodboard import (
    MoodboardBoard,
    MoodboardCollection,
    MoodboardItem,
)
from app.models.planning import BudgetCategory, Expense, Vendor
from app.repositories.project_settings import get_project_settings
from app.services.data_export import EXPORT_MODELS, serialize_record
from app.services.record_deletion import REUSABLE_UNIQUE_FIELDS

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
PAGE_MARGIN = 48
CONTENT_TOP = 774
CONTENT_BOTTOM = 54

CURRENCY_SYMBOLS = {
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
    "CHF": "CHF",
    "BRL": "R$",
}
CURRENCY_FIELDS = frozenset(
    {
        "agreed_price",
        "amount",
        "paid_amount",
        "planned_limit",
        "total_budget",
    }
)
DATE_FIELDS = frozenset(
    {
        "created_at",
        "updated_at",
        "occurred_at",
        "event_date",
        "wedding_date",
        "locked_until",
        "deleted_at",
    }
)
DATE_ONLY_FIELDS = frozenset(
    {
        "deposit_date",
        "due_date",
        "expense_date",
        "final_payment_date",
        "payment_date",
    }
)
AUTHOR_FIELDS = {
    "created_by_id": "Criado por",
    "deleted_by_id": "Eliminado por",
    "updated_by_id": "Última alteração por",
    "user_id": "Utilizador",
}
REFERENCE_MODELS = {
    "category_id": (BudgetCategory, "name"),
    "vendor_id": (Vendor, "company"),
    "expense_id": (Expense, "description"),
    "board_id": (MoodboardBoard, "name"),
    "collection_id": (MoodboardCollection, "name"),
    "item_id": (MoodboardItem, "title"),
}
SECTION_TITLES = {
    "project_settings": "Configurações do projeto",
    "users": "Utilizadores",
    "activities": "Histórico de atividade",
    "record_tombstones": "Registos removidos definitivamente",
    "workspace_records": "Planeamento e comunicação",
    "tasks": "Checklist",
    "guests": "Convidados",
    "vendors": "Fornecedores",
    "budget_categories": "Categorias do orçamento",
    "expenses": "Despesas",
    "payments": "Pagamentos",
    "legal_documents": "Documentos legais",
    "moodboard_boards": "Moodboards",
    "moodboard_collections": "Coleções do moodboard",
    "moodboard_items": "Inspirações",
    "moodboard_inspiration_placements": "Mesa de inspiração",
}
COLUMN_LABELS = {
    "id": "N.º",
    "project_name": "Nome do projeto",
    "partner_one_name": "Primeiro nome",
    "partner_two_name": "Segundo nome",
    "wedding_date": "Data do casamento",
    "wedding_city": "Cidade",
    "wedding_style": "Estilo",
    "wedding_timezone": "Fuso horário",
    "ceremony_venue": "Salão do Reino",
    "reception_venue": "Copo de Água",
    "total_budget": "Orçamento",
    "currency": "Moeda",
    "name": "Nome",
    "title": "Título",
    "description": "Descrição",
    "company": "Empresa",
    "vendor_type": "Tipo",
    "contact_name": "Contacto",
    "phone": "Telefone",
    "email": "E-mail",
    "website": "Website",
    "source_url": "URL de origem",
    "image_url": "Imagem",
    "planned_limit": "Limite",
    "agreed_price": "Preço acordado",
    "paid_amount": "Valor pago",
    "amount": "Valor",
    "status": "Estado",
    "priority": "Prioridade",
    "category": "Categoria",
    "category_id": "Categoria",
    "vendor_id": "Fornecedor",
    "expense_id": "Despesa associada",
    "board_id": "Moodboard",
    "collection_id": "Coleção",
    "item_id": "Inspiração",
    "responsible": "Responsável",
    "assignee": "Responsável",
    "action_type": "Ação",
    "module": "Módulo",
    "occurred_at": "Data e hora",
    "created_at": "Criado em",
    "updated_at": "Última alteração em",
    "is_archived": "Eliminado",
    "is_active": "Conta ativa",
    "is_favorite": "Favorito",
    "entity_type": "Tipo de registo",
    "entity_id": "N.º do registo",
    "deleted_at": "Eliminado em",
    "snapshot_json": "Dados preservados para recuperação técnica",
    "notes": "Notas",
    "comments": "Comentários",
    "tags": "Etiquetas",
    "reference": "Referência",
    "event_date": "Data",
    "due_date": "Data limite",
    "expense_date": "Data da despesa",
    "payment_date": "Data do pagamento",
    "deposit_date": "Data do sinal",
    "final_payment_date": "Pagamento final",
    "attachment_path": "Anexo",
    "contract_path": "Contrato",
    "invoice_path": "Fatura",
    "receipt_path": "Comprovativo",
    "document_path": "Documento",
    "location": "Local",
    "contact": "Contacto",
    "rsvp_status": "Resposta",
    "table_name": "Mesa",
}
TECHNICAL_SETTINGS_FIELDS = frozenset(
    {
        "settings_version",
        "dashboard_show_activity",
        "dashboard_show_countdown",
        "dashboard_show_finance",
        "dashboard_show_moodboard",
        "motion_preference",
    }
)


@dataclass(frozen=True)
class ReportSection:
    """One titled collection of safe, already serialized records."""

    title: str
    records: Sequence[Mapping[str, Any]]


def _pdf_literal(value: str) -> bytes:
    """Encode a PDF literal safely using the built-in WinAnsi character set."""

    encoded = value.encode("cp1252", errors="replace")
    escaped = bytearray()
    for byte in encoded:
        if byte in {40, 41, 92}:  # Parentheses and backslash.
            escaped.extend(b"\\")
            escaped.append(byte)
        elif byte < 32 or byte > 126:
            escaped.extend(f"\\{byte:03o}".encode("ascii"))
        else:
            escaped.append(byte)
    return b"(" + bytes(escaped) + b")"


def _pdf_date(value: datetime) -> str:
    normalized = value.astimezone(UTC)
    return normalized.strftime("D:%Y%m%d%H%M%S+00'00'")


class _PdfFlow:
    """Small A4 flow layout with automatic page breaks."""

    def __init__(self, title: str, subtitle: str) -> None:
        self.title = title
        self.subtitle = subtitle
        self.pages: list[list[bytes]] = []
        self.y = CONTENT_TOP
        self._new_page(first=True)

    def _new_page(self, *, first: bool = False) -> None:
        commands = [
            b"0.984 0.973 0.965 rg 0 0 595 842 re f",
            b"0.973 0.863 0.910 rg 0 806 595 36 re f",
            b"0.847 0.545 0.655 rg 0 804 595 2 re f",
            self._text_command("LV - Wedding Planner", 48, 818, 9, bold=True, color="0.2 0.2 0.2"),
        ]
        self.pages.append(commands)
        self.y = CONTENT_TOP
        if first:
            self._write_wrapped(self.title, size=22, bold=True, color="0.2 0.2 0.2", leading=28)
            self._write_wrapped(
                self.subtitle,
                size=9,
                color="0.35 0.35 0.35",
                leading=13,
            )
            self.y -= 12
        else:
            self._write_wrapped(
                f"{self.title} · continuação",
                size=13,
                bold=True,
                color="0.2 0.2 0.2",
                leading=18,
            )
            self.y -= 7

    @staticmethod
    def _text_command(
        value: str,
        x: float,
        y: float,
        size: float,
        *,
        bold: bool = False,
        color: str = "0.2 0.2 0.2",
    ) -> bytes:
        font = b"/F2" if bold else b"/F1"
        return (
            b"BT "
            + font
            + f" {size:.1f} Tf {color} rg {x:.1f} {y:.1f} Td ".encode("ascii")
            + _pdf_literal(value)
            + b" Tj ET"
        )

    def _ensure(self, height: float) -> None:
        if self.y - height < CONTENT_BOTTOM:
            self._new_page()

    def _wrapped_lines(self, value: str, *, size: float, indent: int = 0) -> list[str]:
        normalized = re.sub(r"\s+", " ", value).strip() or "—"
        available = PAGE_WIDTH - (PAGE_MARGIN * 2) - indent
        characters = max(24, int(available / max(size * 0.51, 1)))
        return textwrap.wrap(
            normalized,
            width=characters,
            break_long_words=True,
            break_on_hyphens=False,
        ) or ["—"]

    def _write_wrapped(
        self,
        value: str,
        *,
        size: float = 9,
        bold: bool = False,
        color: str = "0.2 0.2 0.2",
        leading: float = 13,
        indent: int = 0,
    ) -> None:
        for line in self._wrapped_lines(value, size=size, indent=indent):
            self._ensure(leading)
            self.pages[-1].append(
                self._text_command(
                    line,
                    PAGE_MARGIN + indent,
                    self.y,
                    size,
                    bold=bold,
                    color=color,
                )
            )
            self.y -= leading

    def section(self, title: str, count: int) -> None:
        self._ensure(42)
        self.y -= 5
        self.pages[-1].append(
            f"0.847 0.545 0.655 rg {PAGE_MARGIN} {self.y - 4:.1f} 6 21 re f".encode("ascii")
        )
        self._write_wrapped(
            f"{title} ({count})",
            size=14,
            bold=True,
            color="0.2 0.2 0.2",
            leading=20,
            indent=15,
        )
        self.y -= 5

    def empty(self) -> None:
        self._write_wrapped(
            "Ainda não existem registos nesta área.",
            size=9,
            color="0.45 0.45 0.45",
            leading=14,
        )
        self.y -= 7

    def record(
        self,
        heading: str,
        fields: Iterable[tuple[str, str]],
        *,
        index: int,
    ) -> None:
        self._ensure(40)
        self._write_wrapped(
            f"{index}. {heading}",
            size=10,
            bold=True,
            color="0.38 0.25 0.30",
            leading=15,
        )
        for label, value in fields:
            self._write_wrapped(
                f"{label}: {value}",
                size=8.5,
                color="0.27 0.27 0.27",
                leading=12,
                indent=10,
            )
        self._ensure(9)
        self.pages[-1].append(
            f"0.88 0.83 0.84 RG 0.5 w {PAGE_MARGIN} {self.y:.1f} m "
            f"{PAGE_WIDTH - PAGE_MARGIN} {self.y:.1f} l S".encode("ascii")
        )
        self.y -= 9

    def build(self) -> bytes:
        page_count = len(self.pages)
        for page_number, commands in enumerate(self.pages, start=1):
            commands.append(
                self._text_command(
                    f"Página {page_number} de {page_count}",
                    PAGE_WIDTH - 106,
                    28,
                    8,
                    color="0.42 0.42 0.42",
                )
            )
        return _assemble_pdf(self.pages, title=self.title)


def _assemble_pdf(pages: Sequence[Sequence[bytes]], *, title: str) -> bytes:
    """Assemble complete PDF objects and a standards-compliant cross-reference table."""

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"),
        4: (
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            b"/Encoding /WinAnsiEncoding >>"
        ),
    }
    page_object_ids: list[int] = []
    next_object_id = 5
    for page in pages:
        page_object_id = next_object_id
        content_object_id = next_object_id + 1
        next_object_id += 2
        page_object_ids.append(page_object_id)
        content = b"\n".join(page) + b"\n"
        objects[page_object_id] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            + f"/Contents {content_object_id} 0 R >>".encode("ascii")
        )
        objects[content_object_id] = (
            f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"endstream"
        )
    children = b" ".join(f"{object_id} 0 R".encode("ascii") for object_id in page_object_ids)
    objects[2] = b"<< /Type /Pages /Kids [" + children + f"] /Count {len(pages)} >>".encode("ascii")
    info_object_id = next_object_id
    generated_at = datetime.now(UTC)
    objects[info_object_id] = (
        b"<< /Title "
        + _pdf_literal(title)
        + b" /Author "
        + _pdf_literal("LV - Wedding Planner")
        + b" /Creator "
        + _pdf_literal("LV - Wedding Planner")
        + b" /CreationDate "
        + _pdf_literal(_pdf_date(generated_at))
        + b" >>"
    )

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (info_object_id + 1)
    for object_id in range(1, info_object_id + 1):
        offsets[object_id] = len(output)
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(objects[object_id])
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {info_object_id + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {info_object_id + 1} /Root 1 0 R "
            f"/Info {info_object_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _money(value: Any, currency: str) -> str:
    try:
        amount = Decimal(str(value).replace(",", "."))
        formatted = f"{amount:,.2f}".replace(",", "\u00a0").replace(".", ",")
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    return f"{formatted} {symbol}".strip()


def _format_value(
    field: str,
    value: Any,
    *,
    currency: str,
    user_names: Mapping[int, str],
    reference_names: Mapping[str, Mapping[int, str]],
) -> str:
    if field in AUTHOR_FIELDS:
        if value is None:
            return "Sistema"
        try:
            return user_names.get(int(value), f"Utilizador #{value}")
        except (TypeError, ValueError):
            return str(value)
    if value is None or value == "":
        return "—"
    if field in reference_names:
        try:
            return reference_names[field].get(int(value), f"Registo #{value}")
        except (TypeError, ValueError):
            return str(value)
    if field in CURRENCY_FIELDS:
        return _money(value, currency)
    if field in DATE_FIELDS:
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed.strftime("%d/%m/%Y · %H:%M")
    if field in DATE_ONLY_FIELDS:
        parsed_date = _parse_date(value)
        if parsed_date is not None:
            return parsed_date.strftime("%d/%m/%Y")
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, (datetime, date)):
        return (
            value.strftime("%d/%m/%Y · %H:%M")
            if isinstance(value, datetime)
            else value.strftime("%d/%m/%Y")
        )
    return str(value)


def _record_heading(record: Mapping[str, Any], index: int) -> str:
    for field in ("title", "name", "company", "project_name", "description", "reference"):
        value = record.get(field)
        if value:
            return str(value)
    if record.get("entity_type") and record.get("entity_id") is not None:
        module = str(record.get("module") or "Registo")
        return f"{module} · {record['entity_type']} #{record['entity_id']}"
    record_id = record.get("id")
    return f"Registo #{record_id}" if record_id is not None else f"Registo {index}"


def _report_fields(
    record: Mapping[str, Any],
    *,
    currency: str,
    user_names: Mapping[int, str],
    reference_names: Mapping[str, Mapping[int, str]],
) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for field, value in record.items():
        if field in TECHNICAL_SETTINGS_FIELDS:
            continue
        if field in {"title", "name", "company", "project_name"} and value:
            continue
        label = AUTHOR_FIELDS.get(field, COLUMN_LABELS.get(field, field.replace("_", " ").title()))
        formatted = _format_value(
            field,
            value,
            currency=currency,
            user_names=user_names,
            reference_names=reference_names,
        )
        if formatted == "—" and field not in {"created_by_id", "updated_by_id"}:
            continue
        fields.append((label, formatted))
    return fields


def render_pdf_report(
    *,
    title: str,
    project_name: str,
    sections: Sequence[ReportSection],
    currency: str = "EUR",
    user_names: Mapping[int, str] | None = None,
    reference_names: Mapping[str, Mapping[int, str]] | None = None,
) -> bytes:
    """Render safe report sections into a complete, downloadable PDF."""

    generated = datetime.now().astimezone()
    total_records = sum(len(section.records) for section in sections)
    subtitle = (
        f"{project_name} · Gerado em {generated:%d/%m/%Y às %H:%M} · "
        f"{total_records} registo{'s' if total_records != 1 else ''}"
    )
    flow = _PdfFlow(title, subtitle)
    authors = user_names or {}
    references = reference_names or {}
    for section in sections:
        flow.section(section.title, len(section.records))
        if not section.records:
            flow.empty()
            continue
        for index, record in enumerate(section.records, start=1):
            flow.record(
                _record_heading(record, index),
                _report_fields(
                    record,
                    currency=currency,
                    user_names=authors,
                    reference_names=references,
                ),
                index=index,
            )
    return flow.build()


def _tombstone_snapshots(db: Session) -> dict[tuple[str, int], dict[str, Any]]:
    """Load original values used only to keep human-readable PDFs clean."""

    snapshots: dict[tuple[str, int], dict[str, Any]] = {}
    for tombstone in db.scalars(select(RecordTombstone)).all():
        try:
            snapshot = json.loads(tombstone.snapshot_json)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(snapshot, dict):
            snapshots[(tombstone.entity_type, tombstone.entity_id)] = snapshot
    return snapshots


def _serialize_for_report(
    record: Any,
    tombstone_snapshots: Mapping[tuple[str, int], Mapping[str, Any]],
) -> dict[str, Any]:
    """Use original business labels while retaining the technical source row."""

    serialized = serialize_record(record)
    table_name = str(record.__table__.name)
    original = tombstone_snapshots.get((table_name, record.id), {})
    for field_name in REUSABLE_UNIQUE_FIELDS.get(table_name, ()):
        if field_name in original:
            serialized[field_name] = original[field_name]
    return serialized


def _reference_names(
    db: Session,
    tombstone_snapshots: Mapping[tuple[str, int], Mapping[str, Any]],
) -> dict[str, dict[int, str]]:
    """Resolve foreign keys to the labels people use in the interface."""

    return {
        field: {
            record.id: str(
                tombstone_snapshots.get(
                    (str(model.__table__.name), record.id),
                    {},
                ).get(label_field, getattr(record, label_field))
            )
            for record in db.scalars(select(model).order_by(model.id)).all()
        }
        for field, (model, label_field) in REFERENCE_MODELS.items()
    }


def build_full_pdf(db: Session) -> bytes:
    """Build a human-readable report of all portable planning data."""

    settings = get_project_settings(db, create=False)
    project_name = settings.project_name if settings is not None else "LV - Wedding Planner"
    currency = settings.currency if settings is not None else "EUR"
    users = db.scalars(select(User).order_by(User.id)).all()
    user_names = {user.id: user.name for user in users}
    tombstone_snapshots = _tombstone_snapshots(db)
    sections = [
        ReportSection(
            SECTION_TITLES.get(model.__tablename__, model.__tablename__.replace("_", " ").title()),
            [
                _serialize_for_report(record, tombstone_snapshots)
                for record in db.scalars(select(model)).all()
            ],
        )
        for model in EXPORT_MODELS
    ]
    return render_pdf_report(
        title="Exportação completa do casamento",
        project_name=project_name,
        sections=sections,
        currency=currency,
        user_names=user_names,
        reference_names=_reference_names(db, tombstone_snapshots),
    )


def build_module_pdf(
    db: Session,
    *,
    title: str,
    records: Sequence[Any],
    archived: bool = False,
) -> bytes:
    """Build one filtered module report from its persisted SQLAlchemy rows."""

    settings = get_project_settings(db, create=False)
    project_name = settings.project_name if settings is not None else "LV - Wedding Planner"
    currency = settings.currency if settings is not None else "EUR"
    users = db.scalars(select(User).order_by(User.id)).all()
    tombstone_snapshots = _tombstone_snapshots(db)
    section_title = f"{title} · {'Eliminados' if archived else 'Ativos'}"
    return render_pdf_report(
        title=f"Relatório · {title}",
        project_name=project_name,
        sections=[
            ReportSection(
                section_title,
                [serialize_record(record) for record in records],
            )
        ],
        currency=currency,
        user_names={user.id: user.name for user in users},
        reference_names=_reference_names(db, tombstone_snapshots),
    )
