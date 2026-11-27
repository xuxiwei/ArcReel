"""SaaS: admins read reconciliation reports through the workbench (forwarded with their own token)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from saas.adapter import routes_reconciliation


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch):
    seen: list[tuple[str, str, str]] = []

    async def fake_request(method, path, *, access_token, json_body=None):
        seen.append((method, path, access_token))
        return {"ok": True}

    monkeypatch.setattr("saas.adapter.control_plane_client.control_plane_user_request", fake_request)
    return seen


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes_reconciliation.router, prefix="/api/v1")
    return TestClient(app)


def test_forwards_with_the_callers_token(monkeypatch: pytest.MonkeyPatch, calls) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    client = _client()
    headers = {"Authorization": "Bearer admin-jwt"}
    assert client.get("/api/v1/saas/admin/reconciliation?limit=5", headers=headers).json() == {"ok": True}
    client.post("/api/v1/saas/admin/reconciliation/statements/run?report_date=2026-11-26", headers=headers)
    client.get("/api/v1/saas/admin/reconciliation/2026-11-26", headers=headers)
    assert calls == [
        ("GET", "/v1/admin/reconciliation?limit=5", "admin-jwt"),
        ("POST", "/v1/admin/reconciliation/statements/run?report_date=2026-11-26", "admin-jwt"),
        ("GET", "/v1/admin/reconciliation/2026-11-26", "admin-jwt"),
    ]


def test_self_hosted_404(monkeypatch: pytest.MonkeyPatch, calls) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    assert _client().get("/api/v1/saas/admin/reconciliation").status_code == 404
    assert calls == []


def test_mounted_admin_only() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[3] / "server/app.py").read_text(encoding="utf-8")
    flat = " ".join(source.split())
    assert "saas_reconciliation_router, prefix=\"/api/v1\", dependencies=[Depends(get_current_user), Depends(SAAS_ADMIN_ONLY)]" in flat
