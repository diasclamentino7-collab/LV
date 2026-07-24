from urllib.parse import urlparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import or_, select

from app.core.config import get_settings
from app.core.templating import templates
from app.db.session import SessionLocal
from app.models.moodboard import MoodboardBoard, MoodboardCollection, MoodboardItem
from app.services.activity import record_activity
from app.services.auth_session import authenticated_user
from app.services.csrf import valid_csrf_token

router = APIRouter(prefix="/moodboard")


def user_id(request: Request) -> int | None:
    with SessionLocal() as db:
        user = authenticated_user(db, request)
        return user.id if user is not None else None


def valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def ensure_default_collection(db, owner_id: int) -> MoodboardCollection:
    collection = db.scalar(
        select(MoodboardCollection)
        .where(MoodboardCollection.is_archived.is_(False))
        .order_by(MoodboardCollection.id)
    )
    if collection:
        return collection
    board = MoodboardBoard(name="O nosso casamento", created_by_id=owner_id, updated_by_id=owner_id)
    db.add(board)
    db.flush()
    collection = MoodboardCollection(
        board_id=board.id, name="Inspirações", created_by_id=owner_id, updated_by_id=owner_id
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


@router.get("", response_class=HTMLResponse, include_in_schema=False)
def moodboard(request: Request, q: str = "", favorites: bool = False) -> Response:
    owner_id = user_id(request)
    if owner_id is None:
        return RedirectResponse("/login", status_code=303)
    with SessionLocal() as db:
        ensure_default_collection(db, owner_id)
        statement = select(MoodboardItem).where(MoodboardItem.is_archived.is_(False))
        if q:
            statement = statement.where(
                or_(MoodboardItem.title.ilike(f"%{q}%"), MoodboardItem.tags.ilike(f"%{q}%"))
            )
        if favorites:
            statement = statement.where(MoodboardItem.is_favorite.is_(True))
        items = db.scalars(
            statement.order_by(MoodboardItem.position, MoodboardItem.updated_at.desc())
        ).all()
        collections = db.scalars(
            select(MoodboardCollection)
            .where(MoodboardCollection.is_archived.is_(False))
            .order_by(MoodboardCollection.name)
        ).all()
    return templates.TemplateResponse(
        request,
        "moodboard_list.html",
        {
            "app_name": get_settings().app_name,
            "current_section": "moodboard",
            "items": items,
            "collections": collections,
            "search": q,
            "favorites": favorites,
            "message": request.query_params.get("message"),
        },
    )


@router.get("/new", response_class=HTMLResponse, include_in_schema=False)
def new_item_page(request: Request) -> Response:
    owner_id = user_id(request)
    if owner_id is None:
        return RedirectResponse("/login", status_code=303)
    with SessionLocal() as db:
        ensure_default_collection(db, owner_id)
        collections = db.scalars(
            select(MoodboardCollection).where(MoodboardCollection.is_archived.is_(False))
        ).all()
    return templates.TemplateResponse(
        request,
        "moodboard_form.html",
        {
            "app_name": get_settings().app_name,
            "current_section": "moodboard",
            "item": None,
            "collections": collections,
        },
    )


@router.post("/new", include_in_schema=False)
def create_item(
    request: Request,
    title: str = Form(...),
    collection_id: int = Form(...),
    image_url: str = Form(...),
    source_url: str = Form(""),
    tags: str = Form(""),
    notes: str = Form(""),
    csrf_token: str = Form(""),
) -> RedirectResponse:
    owner_id = user_id(request)
    if owner_id is None:
        return RedirectResponse("/login", status_code=303)
    if not valid_csrf_token(request, csrf_token):
        return RedirectResponse("/moodboard/new?error=csrf", status_code=303)
    if not valid_url(image_url) or (source_url and not valid_url(source_url)):
        return RedirectResponse("/moodboard/new?error=url", status_code=303)
    with SessionLocal() as db:
        item = MoodboardItem(
            collection_id=collection_id,
            title=title.strip(),
            image_url=image_url.strip(),
            source_url=source_url.strip(),
            tags=tags.strip(),
            notes=notes.strip(),
            created_by_id=owner_id,
            updated_by_id=owner_id,
        )
        db.add(item)
        record_activity(db, owner_id, "criou", f"adicionou inspiração: {item.title}", "moodboard")
        db.commit()
    return RedirectResponse("/moodboard?message=created", status_code=303)


@router.get("/{item_id}/edit", response_class=HTMLResponse, include_in_schema=False)
def edit_item_page(request: Request, item_id: int) -> Response:
    if user_id(request) is None:
        return RedirectResponse("/login", status_code=303)
    with SessionLocal() as db:
        item = db.get(MoodboardItem, item_id)
        collections = db.scalars(
            select(MoodboardCollection).where(MoodboardCollection.is_archived.is_(False))
        ).all()
        if item is None or item.is_archived:
            return RedirectResponse("/moodboard", status_code=303)
        db.expunge(item)
    return templates.TemplateResponse(
        request,
        "moodboard_form.html",
        {
            "app_name": get_settings().app_name,
            "current_section": "moodboard",
            "item": item,
            "collections": collections,
        },
    )


@router.post("/{item_id}/edit", include_in_schema=False)
def edit_item(
    request: Request,
    item_id: int,
    title: str = Form(...),
    collection_id: int = Form(...),
    image_url: str = Form(...),
    source_url: str = Form(""),
    tags: str = Form(""),
    notes: str = Form(""),
    csrf_token: str = Form(""),
) -> RedirectResponse:
    owner_id = user_id(request)
    if owner_id is None:
        return RedirectResponse("/login", status_code=303)
    if not valid_csrf_token(request, csrf_token):
        return RedirectResponse(f"/moodboard/{item_id}/edit?error=csrf", status_code=303)
    if not valid_url(image_url) or (source_url and not valid_url(source_url)):
        return RedirectResponse(f"/moodboard/{item_id}/edit?error=url", status_code=303)
    with SessionLocal() as db:
        item = db.get(MoodboardItem, item_id)
        if item and not item.is_archived:
            item.title, item.collection_id, item.image_url = (
                title.strip(),
                collection_id,
                image_url.strip(),
            )
            item.source_url, item.tags, item.notes = source_url.strip(), tags.strip(), notes.strip()
            item.updated_by_id = owner_id
            record_activity(
                db, owner_id, "alterou", f"alterou inspiração: {item.title}", "moodboard"
            )
            db.commit()
    return RedirectResponse("/moodboard?message=updated", status_code=303)


@router.post("/{item_id}/favorite", include_in_schema=False)
def favorite_item(
    request: Request,
    item_id: int,
    csrf_token: str = Form(""),
) -> RedirectResponse:
    owner_id = user_id(request)
    if owner_id is None:
        return RedirectResponse("/login", status_code=303)
    if not valid_csrf_token(request, csrf_token):
        return RedirectResponse("/moodboard?error=csrf", status_code=303)
    with SessionLocal() as db:
        item = db.get(MoodboardItem, item_id)
        if item and not item.is_archived:
            item.is_favorite = not item.is_favorite
            item.updated_by_id = owner_id
            record_activity(
                db, owner_id, "favoritou", f"atualizou favorito: {item.title}", "moodboard"
            )
            db.commit()
    return RedirectResponse("/moodboard", status_code=303)


@router.post("/{item_id}/archive", include_in_schema=False)
def archive_item(
    request: Request,
    item_id: int,
    csrf_token: str = Form(""),
) -> RedirectResponse:
    owner_id = user_id(request)
    if owner_id is None:
        return RedirectResponse("/login", status_code=303)
    if not valid_csrf_token(request, csrf_token):
        return RedirectResponse("/moodboard?error=csrf", status_code=303)
    with SessionLocal() as db:
        item = db.get(MoodboardItem, item_id)
        if item and not item.is_archived:
            item.is_archived = True
            item.updated_by_id = owner_id
            record_activity(
                db, owner_id, "arquivou", f"eliminou inspiração: {item.title}", "moodboard"
            )
            db.commit()
    return RedirectResponse("/moodboard?message=archived", status_code=303)
