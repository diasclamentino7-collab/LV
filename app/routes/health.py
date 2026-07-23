from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health", summary="Application health check")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
