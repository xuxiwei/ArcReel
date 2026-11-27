"""SaaS: instance-wide routers need a platform admin (control-plane users.is_admin)."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from saas.isolation import admin_guard
from saas.isolation.admin_guard import SAAS_ADMIN_ONLY, SAAS_ADMIN_WRITES
from server.auth import EMBEDDED_AGENT_SUB, CurrentUserInfo, get_current_user

ADMIN_TOKEN = "admin-token"
MEMBER_TOKEN = "member-token"


def _app(sub: str = "u1") -> FastAPI:
    router = APIRouter()

    @router.get("/providers")
    async def list_providers():
        return {"ok": True}

    @router.get("/providers/{pid}/credentials")
    async def list_credentials(pid: str):
        return {"ok": True}

    @router.patch("/providers/{pid}/config")
    async def patch_config(pid: str):
        return {"ok": True}

    @router.post("/system/config/recommendation-changes/acknowledge")
    async def acknowledge():
        return {"ok": True}

    storage = APIRouter()

    @storage.get("/object-storage/connection")
    async def get_connection():
        return {"ok": True}

    app = FastAPI()
    app.include_router(router, prefix="/api/v1", dependencies=[Depends(SAAS_ADMIN_WRITES)])
    app.include_router(storage, prefix="/api/v1", dependencies=[Depends(SAAS_ADMIN_ONLY)])
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="u1", sub=sub, role="member", org_id="o1")
    return app


@pytest.fixture(autouse=True)
def saas(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    calls: list[str] = []

    async def fake_fetch(token: str) -> bool:
        calls.append(token)
        return token == ADMIN_TOKEN

    monkeypatch.setattr(admin_guard, "_fetch_is_admin", fake_fetch)
    admin_guard.clear_admin_cache()
    yield calls
    admin_guard.clear_admin_cache()


def _get(client: TestClient, path: str, token: str, method: str = "GET"):
    return client.request(method, f"/api/v1{path}", headers={"Authorization": f"Bearer {token}"})


def test_members_read_but_cannot_write_or_read_secrets() -> None:
    client = TestClient(_app())
    assert _get(client, "/providers", MEMBER_TOKEN).status_code == 200
    assert _get(client, "/providers/ark/credentials", MEMBER_TOKEN).status_code == 403
    assert _get(client, "/providers/ark/config", MEMBER_TOKEN, "PATCH").status_code == 403
    assert _get(client, "/object-storage/connection", MEMBER_TOKEN).status_code == 403
    # The one write every member may make.
    assert _get(client, "/system/config/recommendation-changes/acknowledge", MEMBER_TOKEN, "POST").status_code == 200


def test_platform_admin_can_do_everything() -> None:
    client = TestClient(_app())
    assert _get(client, "/providers/ark/credentials", ADMIN_TOKEN).status_code == 200
    assert _get(client, "/providers/ark/config", ADMIN_TOKEN, "PATCH").status_code == 200
    assert _get(client, "/object-storage/connection", ADMIN_TOKEN).status_code == 200


def test_embedded_agent_is_never_admin(saas) -> None:
    client = TestClient(_app(sub=EMBEDDED_AGENT_SUB))
    assert _get(client, "/object-storage/connection", ADMIN_TOKEN).status_code == 403
    assert saas == []  # refused before asking the control plane
    assert _get(client, "/providers", ADMIN_TOKEN).status_code == 200


def test_admin_status_is_cached_briefly(saas) -> None:
    client = TestClient(_app())
    for _ in range(3):
        assert _get(client, "/object-storage/connection", ADMIN_TOKEN).status_code == 200
    assert saas == [ADMIN_TOKEN]


def test_self_hosted_is_unchanged(monkeypatch: pytest.MonkeyPatch, saas) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    client = TestClient(_app())
    assert _get(client, "/object-storage/connection", MEMBER_TOKEN).status_code == 200
    assert _get(client, "/providers/ark/config", MEMBER_TOKEN, "PATCH").status_code == 200
    assert saas == []


def test_workbench_mounts_guards_on_instance_wide_routers() -> None:
    """Every instance-wide router in server/app.py carries one of the guards."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[3] / "server" / "app.py").read_text(encoding="utf-8")
    assert 'usage.router, prefix="/api/v1", dependencies=[Depends(get_current_user), Depends(SAAS_USAGE_SCOPE)]' in " ".join(source.split())
    for name in ("object_storage", "asset_library", "system", "api_keys", "agent_config",
                 "custom_endpoints", "market_submissions", "official_service"):
        assert f"{name}.router, prefix=\"/api/v1\", dependencies=[Depends(get_current_user), Depends(SAAS_ADMIN_ONLY)]" in " ".join(source.split()), name
    for name in ("providers", "provider_models", "catalog", "system_config", "market", "custom_providers"):
        assert f"{name}.router, prefix=\"/api/v1\", dependencies=[Depends(get_current_user), Depends(SAAS_ADMIN_WRITES)]" in " ".join(source.split()), name
