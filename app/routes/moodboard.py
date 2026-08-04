import math
from urllib.parse import urlparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.templating import templates
from app.db.session import SessionLocal
from app.models.moodboard import (
    MoodboardBoard,
    MoodboardCollection,
    MoodboardInspirationPlacement,
    MoodboardItem,
)
from app.services.activity import record_activity
from app.services.auth_session import authenticated_user
from app.services.csrf import valid_csrf_token

router = APIRouter(prefix="/moodboard")

ALLOWED_VIEWS = {"gallery", "table"}
ALLOWED_SORTS = {"custom", "recent", "title", "favorites"}
PLACEMENT_X_LIMIT = 82.0
PLACEMENT_Y_LIMIT = 76.0
PLACEMENT_ROTATION_LIMIT = 6.0
PLACEMENT_LAYER_LIMIT = 10_000


def user_id(request: Request) -> int | None:
    with SessionLocal() as db:
        user = authenticated_user(db, request)
        return user.id if user is not None else None


def valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return len(value) <= 1000 and parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def valid_item_values(title: str, tags: str, notes: str) -> bool:
    return (
        bool(title.strip())
        and len(title.strip()) <= 200
        and len(tags) <= 300
        and len(notes) <= 10_000
    )


def safe_view(value: str) -> str:
    return value if value in ALLOWED_VIEWS else "gallery"


def safe_sort(value: str) -> str:
    return value if value in ALLOWED_SORTS else "custom"


def clamp_number(value: float, lower: float, upper: float) -> float:
    if not math.isfinite(value):
        return lower
    return round(min(max(value, lower), upper), 2)


def default_placement(index: int, owner_id: int, item_id: int) -> MoodboardInspirationPlacement:
    columns = 4
    rotations = (-2.4, 1.8, -1.1, 2.6, -1.8, 1.2)
    column = index % columns
    row = (index // columns) % 4
    return MoodboardInspirationPlacement(
        item_id=item_id,
        x_percent=4.0 + (column * 24.0),
        y_percent=4.0 + (row * 23.0),
        rotation_degrees=rotations[index % len(rotations)],
        layer=index + 1,
        created_by_id=owner_id,
        updated_by_id=owner_id,
    )


def ensure_item_placements(db, items: list[MoodboardItem], owner_id: int) -> dict[int, dict]:
    item_ids = [item.id for item in items]
    if not item_ids:
        return {}
    ordered_item_ids = list(
        db.scalars(
            select(MoodboardItem.id)
            .where(MoodboardItem.is_archived.is_(False))
            .order_by(MoodboardItem.position, MoodboardItem.id)
        ).all()
    )
    placement_indexes = {item_id: index for index, item_id in enumerate(ordered_item_ids)}
    existing = db.scalars(
        select(MoodboardInspirationPlacement).where(
            MoodboardInspirationPlacement.item_id.in_(item_ids)
        )
    ).all()
    existing_ids = {placement.item_id for placement in existing}
    for item in items:
        if item.id not in existing_ids:
            db.add(
                default_placement(
                    placement_indexes.get(item.id, max(item.id - 1, 0)),
                    owner_id,
                    item.id,
                )
            )
    placements_created = len(existing_ids) != len(item_ids)
    if placements_created:
        try:
            db.commit()
        except IntegrityError:
            # Two collaborators may open the table for the first time together.
            # The unique constraint keeps the winning layout and no item is lost.
            db.rollback()
        existing = db.scalars(
            select(MoodboardInspirationPlacement).where(
                MoodboardInspirationPlacement.item_id.in_(item_ids)
            )
        ).all()
        # SessionLocal expires loaded rows on commit. Refresh the existing item
        # objects before the template receives them outside the session.
        for item in items:
            db.refresh(item)
    return {
        placement.item_id: {
            "x": placement.x_percent,
            "y": placement.y_percent,
            "rotation": placement.rotation_degrees,
            "layer": placement.layer,
        }
        for placement in existing
    }


def ensure_default_collection(db, owner_id: int) -> MoodboardCollection:
    collection = db.scalar(
        select(MoodboardCollection)
        .where(MoodboardCollection.is_archived.is_(False))
        .order_by(MoodboardCollection.id)
    )
    if collection:
        return collection
    board = MoodboardBoard(
        name="O nosso casamento",
        created_by_id=owner_id,
        updated_by_id=owner_id,
    )
    db.add(board)
    db.flush()
    collection = MoodboardCollection(
        board_id=board.id,
        name="Inspirações",
        created_by_id=owner_id,
        updated_by_id=owner_id,
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


def moodboard_redirect(view: str, message: str = "") -> RedirectResponse:
    location = f"/moodboard?view={safe_view(view)}"
    if message:
        location = f"{location}&message={message}"
    return RedirectResponse(location, status_code=303)


def async_request(request: Request) -> bool:
    return request.headers.get("x-requested-with") == "lv-moodboard"


@router.get("", response_class=HTMLResponse, include_in_schema=False)
def moodboard(
    request: Request,
    q: str = "",
    favorites: bool = False,
    collection_id: int | None = None,
    view: str = "gallery",
    sort: str = "custom",
) -> Response:
    owner_id = user_id(request)
    if owner_id is None:
        return RedirectResponse("/login", status_code=303)
    selected_view = safe_view(view)
    selected_sort = safe_sort(sort)
    search = q.strip()[:100]
    with SessionLocal() as db:
        ensure_default_collection(db, owner_id)
        statement = select(MoodboardItem).where(MoodboardItem.is_archived.is_(False))
        if search:
            statement = statement.where(
                or_(
                    MoodboardItem.title.ilike(f"%{search}%"),
                    MoodboardItem.tags.ilike(f"%{search}%"),
                    MoodboardItem.notes.ilike(f"%{search}%"),
                )
            )
        if favorites:
            statement = statement.where(MoodboardItem.is_favorite.is_(True))
        if collection_id is not None:
            statement = statement.where(MoodboardItem.collection_id == collection_id)
        if selected_sort == "recent":
            statement = statement.order_by(MoodboardItem.updated_at.desc(), MoodboardItem.id.desc())
        elif selected_sort == "title":
            statement = statement.order_by(MoodboardItem.title, MoodboardItem.id)
        elif selected_sort == "favorites":
            statement = statement.order_by(
                MoodboardItem.is_favorite.desc(),
                MoodboardItem.position,
                MoodboardItem.id,
            )
        else:
            statement = statement.order_by(
                MoodboardItem.position,
                MoodboardItem.updated_at.desc(),
                MoodboardItem.id,
            )
        items = list(db.scalars(statement).all())
        collections = list(
            db.scalars(
                select(MoodboardCollection)
                .where(MoodboardCollection.is_archived.is_(False))
                .order_by(MoodboardCollection.name)
            ).all()
        )
        collection_names = {collection.id: collection.name for collection in collections}
        placements = ensure_item_placements(db, items, owner_id)
        for collection in collections:
            db.refresh(collection)
    return templates.TemplateResponse(
        request,
        "moodboard_list.html",
        {
            "app_name": get_settings().app_name,
            "current_section": "moodboard",
            "items": items,
            "collections": collections,
            "collection_names": collection_names,
            "selected_collection_id": collection_id,
            "placements": placements,
            "search": search,
            "favorites": favorites,
            "selected_view": selected_view,
            "selected_sort": selected_sort,
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
            select(MoodboardCollection)
            .where(MoodboardCollection.is_archived.is_(False))
            .order_by(MoodboardCollection.name)
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
    if (
        not valid_url(image_url)
        or (source_url and not valid_url(source_url))
        or not valid_item_values(title, tags, notes)
    ):
        return RedirectResponse("/moodboard/new?error=validation", status_code=303)
    with SessionLocal() as db:
        collection = db.get(MoodboardCollection, collection_id)
        if collection is None or collection.is_archived:
            return RedirectResponse("/moodboard/new?error=collection", status_code=303)
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
        db.flush()
        placement_count = db.scalar(select(func.count(MoodboardInspirationPlacement.id))) or 0
        db.add(default_placement(placement_count, owner_id, item.id))
        record_activity(
            db,
            owner_id,
            "criou",
            f"adicionou inspiração: {item.title}",
            "moodboard",
        )
        db.commit()
    return RedirectResponse("/moodboard?message=created", status_code=303)


@router.post("/layout/reset", include_in_schema=False)
def reset_inspiration_layout(
    request: Request,
    csrf_token: str = Form(""),
) -> Response:
    owner_id = user_id(request)
    if owner_id is None:
        return RedirectResponse("/login", status_code=303)
    if not valid_csrf_token(request, csrf_token):
        if async_request(request):
            return JSONResponse({"ok": False, "error": "csrf"}, status_code=403)
        return RedirectResponse("/moodboard?view=table&error=csrf", status_code=303)
    with SessionLocal() as db:
        items = list(
            db.scalars(
                select(MoodboardItem)
                .where(MoodboardItem.is_archived.is_(False))
                .order_by(MoodboardItem.position, MoodboardItem.id)
            ).all()
        )
        placements = {
            placement.item_id: placement
            for placement in db.scalars(select(MoodboardInspirationPlacement)).all()
        }
        for index, item in enumerate(items):
            default = default_placement(index, owner_id, item.id)
            placement = placements.get(item.id)
            if placement is None:
                db.add(default)
                continue
            placement.x_percent = default.x_percent
            placement.y_percent = default.y_percent
            placement.rotation_degrees = default.rotation_degrees
            placement.layer = default.layer
            placement.updated_by_id = owner_id
        record_activity(
            db,
            owner_id,
            "organizou",
            "reorganizou a Mesa de Inspiração",
            "moodboard",
        )
        db.commit()
    if async_request(request):
        return JSONResponse({"ok": True})
    return moodboard_redirect("table", "layout_reset")


@router.get("/{item_id}/edit", response_class=HTMLResponse, include_in_schema=False)
def edit_item_page(request: Request, item_id: int) -> Response:
    if user_id(request) is None:
        return RedirectResponse("/login", status_code=303)
    with SessionLocal() as db:
        item = db.get(MoodboardItem, item_id)
        collections = db.scalars(
            select(MoodboardCollection)
            .where(MoodboardCollection.is_archived.is_(False))
            .order_by(MoodboardCollection.name)
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
    if (
        not valid_url(image_url)
        or (source_url and not valid_url(source_url))
        or not valid_item_values(title, tags, notes)
    ):
        return RedirectResponse(
            f"/moodboard/{item_id}/edit?error=validation",
            status_code=303,
        )
    with SessionLocal() as db:
        collection = db.get(MoodboardCollection, collection_id)
        if collection is None or collection.is_archived:
            return RedirectResponse(
                f"/moodboard/{item_id}/edit?error=collection",
                status_code=303,
            )
        item = db.get(MoodboardItem, item_id)
        if item and not item.is_archived:
            item.title, item.collection_id, item.image_url = (
                title.strip(),
                collection_id,
                image_url.strip(),
            )
            item.source_url, item.tags, item.notes = (
                source_url.strip(),
                tags.strip(),
                notes.strip(),
            )
            item.updated_by_id = owner_id
            record_activity(
                db,
                owner_id,
                "alterou",
                f"alterou inspiração: {item.title}",
                "moodboard",
            )
            db.commit()
    return RedirectResponse("/moodboard?message=updated", status_code=303)


@router.post("/{item_id}/favorite", include_in_schema=False)
def favorite_item(
    request: Request,
    item_id: int,
    csrf_token: str = Form(""),
    return_view: str = Form("gallery"),
) -> Response:
    owner_id = user_id(request)
    if owner_id is None:
        return RedirectResponse("/login", status_code=303)
    if not valid_csrf_token(request, csrf_token):
        if async_request(request):
            return JSONResponse({"ok": False, "error": "csrf"}, status_code=403)
        return RedirectResponse("/moodboard?error=csrf", status_code=303)
    favorite = False
    with SessionLocal() as db:
        item = db.get(MoodboardItem, item_id)
        if item is None or item.is_archived:
            if async_request(request):
                return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
            return moodboard_redirect(return_view)
        item.is_favorite = not item.is_favorite
        item.updated_by_id = owner_id
        favorite = item.is_favorite
        record_activity(
            db,
            owner_id,
            "favoritou",
            f"atualizou favorito: {item.title}",
            "moodboard",
        )
        db.commit()
    if async_request(request):
        return JSONResponse({"ok": True, "favorite": favorite})
    return moodboard_redirect(return_view)


@router.post("/{item_id}/placement", include_in_schema=False)
def save_inspiration_placement(
    request: Request,
    item_id: int,
    x_percent: float = Form(...),
    y_percent: float = Form(...),
    rotation_degrees: float = Form(...),
    layer: int = Form(...),
    csrf_token: str = Form(""),
) -> Response:
    owner_id = user_id(request)
    if owner_id is None:
        return JSONResponse({"ok": False, "error": "authentication"}, status_code=401)
    if not valid_csrf_token(request, csrf_token):
        return JSONResponse({"ok": False, "error": "csrf"}, status_code=403)
    def apply_placement_fields(target: MoodboardInspirationPlacement) -> None:
        target.x_percent = clamp_number(x_percent, 0.0, PLACEMENT_X_LIMIT)
        target.y_percent = clamp_number(y_percent, 0.0, PLACEMENT_Y_LIMIT)
        target.rotation_degrees = clamp_number(
            rotation_degrees,
            -PLACEMENT_ROTATION_LIMIT,
            PLACEMENT_ROTATION_LIMIT,
        )
        target.layer = max(1, min(layer, PLACEMENT_LAYER_LIMIT))
        target.updated_by_id = owner_id

    with SessionLocal() as db:
        item = db.get(MoodboardItem, item_id)
        if item is None or item.is_archived:
            return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
        placement = db.scalar(
            select(MoodboardInspirationPlacement).where(
                MoodboardInspirationPlacement.item_id == item_id
            )
        )
        is_new = placement is None
        if placement is None:
            placement = default_placement(0, owner_id, item_id)
            db.add(placement)
        apply_placement_fields(placement)
        record_activity(
            db,
            owner_id,
            "organizou",
            f"reposicionou inspiração: {item.title}",
            "moodboard",
        )
        if is_new:
            try:
                db.commit()
            except IntegrityError:
                # Two collaborators may drag the same never-before-placed item
                # at the same time; the unique constraint on item_id keeps one
                # row. Re-apply this move on top of the winning row instead of
                # silently dropping it.
                db.rollback()
                placement = db.scalar(
                    select(MoodboardInspirationPlacement).where(
                        MoodboardInspirationPlacement.item_id == item_id
                    )
                )
                if placement is None:
                    return JSONResponse({"ok": False, "error": "conflict"}, status_code=409)
                apply_placement_fields(placement)
                record_activity(
                    db,
                    owner_id,
                    "organizou",
                    f"reposicionou inspiração: {item.title}",
                    "moodboard",
                )
                db.commit()
        else:
            db.commit()
        payload = {
            "ok": True,
            "x": placement.x_percent,
            "y": placement.y_percent,
            "rotation": placement.rotation_degrees,
            "layer": placement.layer,
        }
    return JSONResponse(payload)


@router.post("/{item_id}/reorder", include_in_schema=False)
def reorder_item(
    request: Request,
    item_id: int,
    direction: str = Form(...),
    csrf_token: str = Form(""),
    return_view: str = Form("gallery"),
) -> RedirectResponse:
    owner_id = user_id(request)
    if owner_id is None:
        return RedirectResponse("/login", status_code=303)
    if not valid_csrf_token(request, csrf_token):
        return RedirectResponse("/moodboard?error=csrf", status_code=303)
    if direction not in {"previous", "next"}:
        return moodboard_redirect(return_view)
    with SessionLocal() as db:
        items = list(
            db.scalars(
                select(MoodboardItem)
                .where(MoodboardItem.is_archived.is_(False))
                .order_by(MoodboardItem.position, MoodboardItem.updated_at.desc())
            ).all()
        )
        current_index = next(
            (index for index, item in enumerate(items) if item.id == item_id),
            None,
        )
        if current_index is None:
            return moodboard_redirect(return_view)
        target_index = current_index + (-1 if direction == "previous" else 1)
        if 0 <= target_index < len(items):
            items[current_index], items[target_index] = items[target_index], items[current_index]
            for position, item in enumerate(items, start=1):
                item.position = position
                if item.id == item_id:
                    item.updated_by_id = owner_id
            record_activity(
                db,
                owner_id,
                "organizou",
                f"alterou a ordem de: {items[target_index].title}",
                "moodboard",
            )
            db.commit()
    return moodboard_redirect(return_view, "reordered")


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
                db,
                owner_id,
                "arquivou",
                f"eliminou inspiração: {item.title}",
                "moodboard",
            )
            db.commit()
    return RedirectResponse("/moodboard?message=archived", status_code=303)
