from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import app.routes.health as health_routes
from app.main import app


def test_health_check() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_check_returns_503_when_database_is_unavailable(monkeypatch) -> None:
    def unavailable_session():
        raise OperationalError("SELECT 1", {}, RuntimeError("database unavailable"))

    monkeypatch.setattr(health_routes, "SessionLocal", unavailable_session)

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "unavailable",
    }
