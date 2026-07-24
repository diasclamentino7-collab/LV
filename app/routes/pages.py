"""Authenticated CRUD views for the wedding-planning modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import Select, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.templating import templates
from app.db.session import SessionLocal
from app.models.core import WorkspaceRecord
from app.models.planning import BudgetCategory, Expense, Guest, LegalDocument, Payment, Task, Vendor
from app.repositories.project_settings import get_project_settings
from app.services.activity import record_activity
from app.services.auth_session import authenticated_user
from app.services.budget import budget_snapshot, serialize_budget_snapshot
from app.services.csrf import valid_csrf_token
from app.services.record_deletion import create_tombstone, is_tombstoned, not_tombstoned

router = APIRouter()


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"
    options: tuple[str, ...] = ()
    required: bool = False


@dataclass(frozen=True)
class Module:
    slug: str
    title: str
    description: str
    model: type[Any] | None = None
    fields: tuple[Field, ...] = ()
    legacy_slugs: tuple[str, ...] = ()


COMMON_FIELDS = (
    Field("title", "Título"),
    Field("description", "Descrição", "textarea"),
    Field("status", "Estado", "select", ("Pendente", "Em curso", "Concluído")),
    Field("event_date", "Data", "date"),
)
MODULES = {
    "checklist": Module(
        "checklist",
        "Checklist",
        "Tarefas, prioridades e responsáveis.",
        Task,
        (
            Field("title", "Título"),
            Field("description", "Descrição", "textarea"),
            Field("category", "Categoria"),
            Field("priority", "Prioridade", "select", ("Baixa", "Média", "Alta")),
            Field("assignee", "Responsável"),
            Field("due_date", "Data limite", "date"),
            Field("status", "Estado", "select", ("Pendente", "Em curso", "Concluído")),
            Field("tags", "Etiquetas"),
            Field("comments", "Comentários", "textarea"),
        ),
    ),
    "guests": Module(
        "guests",
        "Convidados",
        "Lista, respostas e necessidades dos convidados.",
        Guest,
        (
            Field("name", "Nome"),
            Field("congregation", "Congregação"),
            Field("sex", "Sexo", "select", ("", "Feminino", "Masculino")),
            Field("side", "Parte", "select", ("", "Noivo", "Noiva")),
            Field("age_group", "Grupo", "select", ("Adulto", "Criança")),
            Field("rsvp_status", "Resposta", "select", ("Pendente", "Confirmado", "Recusado")),
            Field("table_name", "Mesa"),
            Field("phone", "Telefone"),
            Field("email", "Email"),
            Field("dietary_requirements", "Restrições alimentares", "textarea"),
            Field("special_needs", "Necessidades especiais", "textarea"),
            Field("notes", "Notas", "textarea"),
        ),
    ),
    "vendors": Module(
        "vendors",
        "Fornecedores",
        "Contactos, acordos e pagamentos aos fornecedores.",
        Vendor,
        (
            Field("vendor_type", "Tipo de fornecedor"),
            Field("company", "Empresa"),
            Field("contact_name", "Pessoa de contacto"),
            Field("phone", "Telefone"),
            Field("email", "Email"),
            Field("website", "Website"),
            Field("agreed_price", "Preço acordado", "number"),
            Field("paid_amount", "Valor pago", "number"),
            Field("deposit_date", "Data do sinal", "date"),
            Field("final_payment_date", "Pagamento final", "date"),
            Field("notes", "Observações", "textarea"),
        ),
    ),
    "budget": Module(
        "budget",
        "Orçamento",
        "Limites planeados por categoria e controlo financeiro.",
        BudgetCategory,
        (Field("name", "Categoria"), Field("planned_limit", "Limite previsto", "number")),
    ),
    "payments": Module(
        "payments",
        "Pagamentos",
        "Livro central de pagamentos ligado ao orçamento e fornecedores.",
        Payment,
        (
            Field("category_id", "Categoria", "category", required=True),
            Field("vendor_id", "Fornecedor", "vendor"),
            Field("amount", "Valor", "number", required=True),
            Field("payment_date", "Data", "date", required=True),
            Field("status", "Estado", "select", ("Pago", "Pendente")),
            Field("reference", "Referência"),
            Field("notes", "Notas", "textarea"),
        ),
    ),
    "expenses": Module(
        "expenses",
        "Despesas",
        "Despesas atuais que alimentam automaticamente o resumo financeiro.",
        Expense,
        (
            Field("category_id", "Categoria", "category", required=True),
            Field("vendor_id", "Fornecedor", "vendor"),
            Field("description", "Descrição", required=True),
            Field("amount", "Valor", "number", required=True),
            Field("expense_date", "Data", "date", required=True),
            Field("status", "Estado", "select", ("Pendente", "Confirmada", "Cancelada")),
            Field("notes", "Notas", "textarea"),
        ),
    ),
    "legal-process": Module(
        "legal-process",
        "Processo Legal",
        "Documentos, prazos e responsáveis.",
        LegalDocument,
        (
            Field("document_type", "Tipo"),
            Field("title", "Documento"),
            Field("status", "Estado", "select", ("Pendente", "Em curso", "Concluído")),
            Field("due_date", "Data limite", "date"),
            Field("responsible", "Responsável"),
            Field("notes", "Notas", "textarea"),
        ),
    ),
    "kingdom-hall": Module(
        "kingdom-hall",
        "Salão do Reino · Cerimónia",
        "Programa, discurso, responsáveis e coordenação da cerimónia.",
        None,
        COMMON_FIELDS,
        ("ceremony",),
    ),
    "communication": Module(
        "communication",
        "Comunicação",
        "Notas, ideias, decisões e lembretes partilhados.",
        None,
        (
            Field("title", "Título"),
            Field("description", "Descrição", "textarea"),
            Field(
                "status",
                "Categoria",
                "select",
                ("Nota", "Ideia", "Decisão", "Lembrete", "Tarefa rápida"),
            ),
            Field("event_date", "Data", "date"),
        ),
    ),
    "reception": Module(
        "reception",
        "Copo de Água · Festa",
        "Local, contactos e decisões para a festa do grande dia.",
        None,
        (
            Field("title", "Nome do local / elemento"),
            Field("location", "Zona / Localização"),
            Field("contact", "Contacto"),
            Field("source_url", "URL", "url"),
            Field("description", "Detalhes / Notas", "textarea"),
            Field("event_date", "Data / Hora", "datetime-local"),
            Field(
                "status",
                "Estado",
                "select",
                (
                    "A pesquisar",
                    "Visitada",
                    "Pré-selecionada",
                    "Escolhida",
                    "Pendente",
                    "Em curso",
                    "Concluído",
                ),
            ),
        ),
        ("quinta",),
    ),
}
for slug, title in {
    "table-plan": "Plano de Mesas",
    "timeline": "Cronograma",
    "attire": "Roupa",
    "honeymoon": "Lua de Mel",
    "home": "Casa",
    "gifts": "Presentes",
    "documents": "Documentos",
    "settings": "Configurações",
}.items():
    MODULES[slug] = Module(
        slug, title, f"Registos e decisões de {title.lower()}.", None, COMMON_FIELDS
    )

# Keep old URLs and open forms compatible while presenting only the consolidated
# modules in the interface.
MODULES["ceremony"] = MODULES["kingdom-hall"]
MODULES["quinta"] = MODULES["reception"]

GLOBAL_DELETED_MODULES = tuple(
    slug for slug in MODULES if slug not in {"ceremony", "quinta", "settings"}
)


def logged_user_id(request: Request) -> int | None:
    return request.session.get("user_id")


def require_login(request: Request) -> RedirectResponse | None:
    with SessionLocal() as db:
        if authenticated_user(db, request) is None:
            return RedirectResponse("/login", status_code=303)
    return None


def value_for(field: Field, raw: str) -> Any:
    if field.kind in {"category", "vendor"}:
        return int(raw) if raw else None
    if not raw:
        return (
            None
            if field.kind in {"date", "datetime-local"}
            else Decimal("0")
            if field.kind == "number"
            else ""
        )
    if field.kind == "date":
        return date.fromisoformat(raw)
    if field.kind == "datetime-local":
        return datetime.fromisoformat(raw)
    if field.kind == "number":
        try:
            return Decimal(raw.replace(",", "."))
        except InvalidOperation:
            return Decimal("0")
    return raw.strip()


def module_query(spec: Module, search: str, archived: bool = False) -> Select[Any]:
    model = spec.model or WorkspaceRecord
    statement = select(model).where(
        model.is_archived.is_(archived),
        not_tombstoned(model),
    )
    if spec.model is None:
        statement = statement.where(WorkspaceRecord.module.in_((spec.slug, *spec.legacy_slugs)))
        if search:
            statement = statement.where(
                or_(
                    WorkspaceRecord.title.ilike(f"%{search}%"),
                    WorkspaceRecord.description.ilike(f"%{search}%"),
                )
            )
    elif search:
        title_column = (
            getattr(model, "title", None)
            or getattr(model, "name", None)
            or getattr(model, "company", None)
            or getattr(model, "description", None)
            or getattr(model, "reference", None)
        )
        if title_column is not None:
            statement = statement.where(title_column.ilike(f"%{search}%"))
    return statement.order_by(model.updated_at.desc())


def record_for(spec: Module, db: Session, record_id: int) -> Any | None:
    model = spec.model or WorkspaceRecord
    record = db.get(model, record_id)
    valid_modules = (spec.slug, *spec.legacy_slugs)
    if (
        record is None
        or record.is_archived
        or is_tombstoned(db, model, record_id)
        or (spec.model is None and record.module not in valid_modules)
    ):
        return None
    return record


def save_values(spec: Module, record: Any, values: dict[str, str]) -> None:
    for field in spec.fields:
        setattr(record, field.name, value_for(field, values.get(field.name, "")))


def relation_choices(db: Session) -> dict[str, list[Any]]:
    return {
        "categories": list(
            db.scalars(
                select(BudgetCategory)
                .where(
                    BudgetCategory.is_archived.is_(False),
                    not_tombstoned(BudgetCategory),
                )
                .order_by(BudgetCategory.name)
            ).all()
        ),
        "vendors": list(
            db.scalars(
                select(Vendor)
                .where(
                    Vendor.is_archived.is_(False),
                    not_tombstoned(Vendor),
                )
                .order_by(Vendor.company)
            ).all()
        ),
    }


def record_label(record: Any) -> str:
    label = (
        getattr(record, "title", None)
        or getattr(record, "name", None)
        or getattr(record, "company", None)
        or getattr(record, "description", None)
    )
    if label:
        return str(label)
    if isinstance(record, Payment):
        return f"Pagamento {record.amount}"
    return f"Registo #{record.id}"


def deleted_redirect(
    slug: str,
    return_to: str,
    *,
    message: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Return only to known internal deleted-record views."""

    base = "/deleted" if return_to == "deleted" else f"/{slug}?archived=true"
    parameter = f"message={message}" if message else f"error={error}"
    separator = "&" if "?" in base else "?"
    return RedirectResponse(f"{base}{separator}{parameter}", status_code=303)


@router.get("/ceremony", include_in_schema=False)
def legacy_ceremony_page() -> RedirectResponse:
    return RedirectResponse("/kingdom-hall", status_code=308)


@router.get("/quinta", include_in_schema=False)
def legacy_quinta_page() -> RedirectResponse:
    return RedirectResponse("/reception", status_code=308)


@router.get("/api/budget-summary", include_in_schema=False)
def budget_summary_api(request: Request, q: str = "") -> JSONResponse:
    """Return current persisted budget values for lightweight live updates."""

    search = q.strip()[:100]
    with SessionLocal() as db:
        user = authenticated_user(db, request)
        if user is None:
            return JSONResponse(
                {"detail": "Sessão não autenticada."},
                status_code=401,
                headers={"Cache-Control": "no-store"},
            )
        settings = get_project_settings(db, user_id=user.id)
        total_budget = settings.total_budget if settings is not None else "0"
        currency = settings.currency if settings is not None else "EUR"
        snapshot = budget_snapshot(db, total_budget, search=search)
        payload = serialize_budget_snapshot(snapshot, currency=currency)
    return JSONResponse(
        payload,
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/deleted", response_class=HTMLResponse, include_in_schema=False)
def deleted_records_page(request: Request, q: str = "") -> Response:
    """Show every recoverable archived record in one authenticated view."""

    if redirect := require_login(request):
        return redirect
    search = q.strip()[:100]
    deleted_records: list[dict[str, Any]] = []
    with SessionLocal() as db:
        for slug in GLOBAL_DELETED_MODULES:
            spec = MODULES[slug]
            records = db.scalars(module_query(spec, search, archived=True)).all()
            deleted_records.extend(
                {
                    "id": record.id,
                    "label": record_label(record),
                    "module_slug": slug,
                    "module_title": spec.title,
                    "updated_at": record.updated_at,
                }
                for record in records
            )
    deleted_records.sort(
        key=lambda item: item["updated_at"].isoformat() if item["updated_at"] else "",
        reverse=True,
    )
    return templates.TemplateResponse(
        request,
        "deleted.html",
        {
            "app_name": get_settings().app_name,
            "current_section": "deleted",
            "records": deleted_records,
            "search": search,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{slug}", response_class=HTMLResponse, include_in_schema=False)
def module_page(request: Request, slug: str, q: str = "", archived: bool = False) -> Response:
    if redirect := require_login(request):
        return redirect
    spec = MODULES.get(slug)
    if spec is None:
        return RedirectResponse("/dashboard", status_code=303)
    q = q.strip()[:100]
    with SessionLocal() as db:
        records = db.scalars(module_query(spec, q, archived)).all()
        record_labels = {record.id: record_label(record) for record in records}
        budget_data = None
        if slug == "budget" and not archived:
            settings = get_project_settings(
                db,
                user_id=logged_user_id(request),
            )
            budget_data = budget_snapshot(
                db,
                settings.total_budget if settings is not None else "0",
                search=q,
            )
    return templates.TemplateResponse(
        request,
        "budget.html" if slug == "budget" else "module_list.html",
        {
            "app_name": get_settings().app_name,
            "current_section": slug,
            "module": spec,
            "records": records,
            "search": q,
            "record_labels": record_labels,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
            "show_archived": archived,
            "budget_data": budget_data,
        },
    )


@router.get("/{slug}/new", response_class=HTMLResponse, include_in_schema=False)
def new_record(request: Request, slug: str) -> Response:
    if redirect := require_login(request):
        return redirect
    spec = MODULES.get(slug)
    if spec is None:
        return RedirectResponse("/dashboard", status_code=303)
    with SessionLocal() as db:
        choices = relation_choices(db)
    return templates.TemplateResponse(
        request,
        "module_form.html",
        {
            "app_name": get_settings().app_name,
            "current_section": slug,
            "module": spec,
            "record": None,
            **choices,
        },
    )


@router.post("/{slug}/new", include_in_schema=False)
async def create_record(request: Request, slug: str) -> RedirectResponse:
    if redirect := require_login(request):
        return redirect
    spec = MODULES.get(slug)
    if spec is None:
        return RedirectResponse("/dashboard", status_code=303)
    values = {key: str(value) for key, value in (await request.form()).items()}
    if not valid_csrf_token(request, values.pop("csrf_token", "")):
        return RedirectResponse(f"/{slug}/new?error=csrf", status_code=303)
    with SessionLocal() as db:
        try:
            record = spec.model() if spec.model else WorkspaceRecord(module=spec.slug)
            save_values(spec, record, values)
            record.created_by_id = logged_user_id(request)
            record.updated_by_id = logged_user_id(request)
            db.add(record)
            record_name = record_label(record)
            record_activity(
                db,
                logged_user_id(request),
                "criou",
                f"adicionou {spec.title.lower()}: {record_name}",
                spec.slug,
            )
            db.commit()
        except (IntegrityError, ValueError):
            db.rollback()
            return RedirectResponse(f"/{slug}/new?error=invalid", status_code=303)
    return RedirectResponse(f"/{slug}?message=created", status_code=303)


@router.get("/{slug}/{record_id}/edit", response_class=HTMLResponse, include_in_schema=False)
def edit_record(request: Request, slug: str, record_id: int) -> Response:
    if redirect := require_login(request):
        return redirect
    spec = MODULES.get(slug)
    if spec is None:
        return RedirectResponse("/dashboard", status_code=303)
    with SessionLocal() as db:
        record = record_for(spec, db, record_id)
        if record is None:
            return RedirectResponse(f"/{slug}", status_code=303)
        choices = relation_choices(db)
        db.expunge(record)
    return templates.TemplateResponse(
        request,
        "module_form.html",
        {
            "app_name": get_settings().app_name,
            "current_section": slug,
            "module": spec,
            "record": record,
            **choices,
        },
    )


@router.post("/{slug}/{record_id}/edit", include_in_schema=False)
async def update_record(request: Request, slug: str, record_id: int) -> RedirectResponse:
    if redirect := require_login(request):
        return redirect
    spec = MODULES.get(slug)
    if spec is None:
        return RedirectResponse("/dashboard", status_code=303)
    values = {key: str(value) for key, value in (await request.form()).items()}
    if not valid_csrf_token(request, values.pop("csrf_token", "")):
        return RedirectResponse(f"/{slug}/{record_id}/edit?error=csrf", status_code=303)
    with SessionLocal() as db:
        record = record_for(spec, db, record_id)
        if record is not None:
            try:
                save_values(spec, record, values)
                record.updated_by_id = logged_user_id(request)
                record_activity(
                    db,
                    logged_user_id(request),
                    "alterou",
                    f"alterou {spec.title.lower()}",
                    spec.slug,
                )
                db.commit()
            except (IntegrityError, ValueError):
                db.rollback()
                return RedirectResponse(f"/{slug}/{record_id}/edit?error=invalid", status_code=303)
    return RedirectResponse(f"/{slug}?message=updated", status_code=303)


@router.post("/{slug}/{record_id}/archive", include_in_schema=False)
def archive_record(
    request: Request,
    slug: str,
    record_id: int,
    csrf_token: str = Form(""),
) -> RedirectResponse:
    if redirect := require_login(request):
        return redirect
    if not valid_csrf_token(request, csrf_token):
        return RedirectResponse(f"/{slug}?error=csrf", status_code=303)
    spec = MODULES.get(slug)
    if spec is not None:
        with SessionLocal() as db:
            record = record_for(spec, db, record_id)
            if record is not None:
                record.is_archived = True
                record.updated_by_id = logged_user_id(request)
                record_activity(
                    db,
                    logged_user_id(request),
                    "arquivou",
                    f"arquivou {spec.title.lower()}",
                    spec.slug,
                )
                db.commit()
    return RedirectResponse(f"/{slug}?message=archived", status_code=303)


@router.post("/{slug}/{record_id}/restore", include_in_schema=False)
def restore_record(
    request: Request,
    slug: str,
    record_id: int,
    csrf_token: str = Form(""),
    return_to: str = "",
) -> RedirectResponse:
    if redirect := require_login(request):
        return redirect
    if not valid_csrf_token(request, csrf_token):
        return deleted_redirect(slug, return_to, error="csrf")
    spec = MODULES.get(slug)
    if spec is not None:
        with SessionLocal() as db:
            model = spec.model or WorkspaceRecord
            record = db.get(model, record_id)
            valid_modules = (spec.slug, *spec.legacy_slugs)
            belongs_to_module = spec.model is not None or (
                record is not None and record.module in valid_modules
            )
            if (
                record is not None
                and record.is_archived
                and belongs_to_module
                and not is_tombstoned(db, model, record_id)
            ):
                record.is_archived = False
                record.updated_by_id = logged_user_id(request)
                record_activity(
                    db,
                    logged_user_id(request),
                    "restaurou",
                    f"restaurou {spec.title.lower()}",
                    spec.slug,
                )
                db.commit()
    if return_to == "deleted":
        return deleted_redirect(slug, return_to, message="restored")
    return RedirectResponse(f"/{slug}?message=restored", status_code=303)


@router.post(
    "/{slug}/{record_id}/delete-permanently",
    include_in_schema=False,
)
def permanently_delete_record(
    request: Request,
    slug: str,
    record_id: int,
    csrf_token: str = Form(""),
    confirmation: str = Form(""),
    return_to: str = "",
) -> RedirectResponse:
    """Remove an archived record from the UI without erasing its database row."""

    if redirect := require_login(request):
        return redirect
    if not valid_csrf_token(request, csrf_token):
        return deleted_redirect(slug, return_to, error="csrf")
    if confirmation.strip() != "APAGAR":
        return deleted_redirect(slug, return_to, error="confirmation")
    spec = MODULES.get(slug)
    if spec is None:
        return RedirectResponse("/deleted", status_code=303)

    with SessionLocal() as db:
        model = spec.model or WorkspaceRecord
        record = db.get(model, record_id)
        valid_modules = (spec.slug, *spec.legacy_slugs)
        belongs_to_module = spec.model is not None or (
            record is not None and record.module in valid_modules
        )
        if record is None or not record.is_archived or not belongs_to_module:
            return deleted_redirect(slug, return_to, error="not_archived")
        if is_tombstoned(db, model, record_id):
            return deleted_redirect(slug, return_to, message="permanently_deleted")

        user_id = logged_user_id(request)
        record_name = record_label(record)
        record.updated_by_id = user_id
        create_tombstone(
            db,
            record,
            module=spec.slug,
            user_id=user_id,
        )
        record_activity(
            db,
            user_id,
            "eliminou definitivamente",
            (
                f"removeu {spec.title.lower()} da interface: {record_name}; "
                "a cópia técnica foi preservada"
            ),
            spec.slug,
        )
        try:
            db.commit()
        except IntegrityError:
            # A second simultaneous request may have inserted the same marker.
            # The unique tombstone keeps the operation idempotent.
            db.rollback()

    return deleted_redirect(slug, return_to, message="permanently_deleted")
