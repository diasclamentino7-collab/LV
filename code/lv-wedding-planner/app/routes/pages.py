"""Authenticated CRUD views for the wedding-planning modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, get_settings
from app.db.session import SessionLocal
from app.models.core import WorkspaceRecord
from app.models.planning import BudgetCategory, Guest, LegalDocument, Task, Vendor
from app.services.activity import record_activity

router = APIRouter()
templates = Jinja2Templates(directory=PROJECT_ROOT / "app" / "templates")


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Module:
    slug: str
    title: str
    description: str
    model: type[Any] | None = None
    fields: tuple[Field, ...] = ()


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
        "Salão do Reino",
        "Informações, programa, oficiante, discurso e coordenação.",
        None,
        COMMON_FIELDS,
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
}
for slug, title in {
    "table-plan": "Plano de Mesas",
    "timeline": "Cronograma",
    "ceremony": "Cerimónia",
    "reception": "Receção",
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


def logged_user_id(request: Request) -> int | None:
    return request.session.get("user_id")


def require_login(request: Request) -> RedirectResponse | None:
    if logged_user_id(request) is None:
        return RedirectResponse("/login", status_code=303)
    return None


def value_for(field: Field, raw: str) -> Any:
    if not raw:
        return None if field.kind == "date" else Decimal("0") if field.kind == "number" else ""
    if field.kind == "date":
        return date.fromisoformat(raw)
    if field.kind == "number":
        try:
            return Decimal(raw.replace(",", "."))
        except InvalidOperation:
            return Decimal("0")
    return raw.strip()


def module_query(spec: Module, search: str) -> Select[Any]:
    model = spec.model or WorkspaceRecord
    statement = select(model).where(model.is_archived.is_(False))
    if spec.model is None:
        statement = statement.where(WorkspaceRecord.module == spec.slug)
        if search:
            statement = statement.where(
                or_(
                    WorkspaceRecord.title.ilike(f"%{search}%"),
                    WorkspaceRecord.description.ilike(f"%{search}%"),
                )
            )
    elif search:
        title_column = getattr(
            model, "title", getattr(model, "name", getattr(model, "company", None))
        )
        statement = statement.where(title_column.ilike(f"%{search}%"))
    return statement.order_by(model.updated_at.desc())


def record_for(spec: Module, db: Session, record_id: int) -> Any | None:
    model = spec.model or WorkspaceRecord
    record = db.get(model, record_id)
    if record is None or record.is_archived or (spec.model is None and record.module != spec.slug):
        return None
    return record


def save_values(spec: Module, record: Any, values: dict[str, str]) -> None:
    for field in spec.fields:
        setattr(record, field.name, value_for(field, values.get(field.name, "")))


@router.get("/{slug}", response_class=HTMLResponse, include_in_schema=False)
def module_page(request: Request, slug: str, q: str = "") -> Response:
    if redirect := require_login(request):
        return redirect
    spec = MODULES.get(slug)
    if spec is None:
        return RedirectResponse("/dashboard", status_code=303)
    with SessionLocal() as db:
        records = db.scalars(module_query(spec, q)).all()
    return templates.TemplateResponse(
        request,
        "module_list.html",
        {
            "app_name": get_settings().app_name,
            "current_section": slug,
            "module": spec,
            "records": records,
            "search": q,
        },
    )


@router.get("/{slug}/new", response_class=HTMLResponse, include_in_schema=False)
def new_record(request: Request, slug: str) -> Response:
    if redirect := require_login(request):
        return redirect
    spec = MODULES.get(slug)
    if spec is None:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        request,
        "module_form.html",
        {
            "app_name": get_settings().app_name,
            "current_section": slug,
            "module": spec,
            "record": None,
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
    with SessionLocal() as db:
        record = spec.model() if spec.model else WorkspaceRecord(module=slug)
        save_values(spec, record, values)
        record.created_by_id = logged_user_id(request)
        record.updated_by_id = logged_user_id(request)
        db.add(record)
        record_name = (
            getattr(record, "title", None)
            or getattr(record, "name", None)
            or getattr(record, "company", "registo")
        )
        record_activity(
            db,
            logged_user_id(request),
            "criou",
            f"adicionou {spec.title.lower()}: {record_name}",
            slug,
        )
        db.commit()
    return RedirectResponse(f"/{slug}", status_code=303)


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
        db.expunge(record)
    return templates.TemplateResponse(
        request,
        "module_form.html",
        {
            "app_name": get_settings().app_name,
            "current_section": slug,
            "module": spec,
            "record": record,
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
    with SessionLocal() as db:
        record = record_for(spec, db, record_id)
        if record is not None:
            save_values(spec, record, values)
            record.updated_by_id = logged_user_id(request)
            record_activity(
                db, logged_user_id(request), "alterou", f"alterou {spec.title.lower()}", slug
            )
            db.commit()
    return RedirectResponse(f"/{slug}", status_code=303)


@router.post("/{slug}/{record_id}/archive", include_in_schema=False)
def archive_record(request: Request, slug: str, record_id: int) -> RedirectResponse:
    if redirect := require_login(request):
        return redirect
    spec = MODULES.get(slug)
    if spec is not None:
        with SessionLocal() as db:
            record = record_for(spec, db, record_id)
            if record is not None:
                record.is_archived = True
                record.updated_by_id = logged_user_id(request)
                record_activity(
                    db, logged_user_id(request), "arquivou", f"arquivou {spec.title.lower()}", slug
                )
                db.commit()
    return RedirectResponse(f"/{slug}", status_code=303)
