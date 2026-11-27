"""SaaS: the admin console reads assets and per-user activity across organisations."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import lib.db.models  # noqa: F401  (registers every table, ``users`` included)
from lib.db.base import Base
from lib.db.models.api_call import ApiCall
from lib.db.models.asset import Asset
from saas.adapter import routes_admin_workbench as admin
from server.auth import CurrentUserInfo, get_current_user


@pytest.fixture
def factory(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'wb.db'}")
    tables = [Base.metadata.tables[name] for name in ("users", "assets", "asset_derivatives", "api_calls")]

    import asyncio

    async def setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as s:
            for org, name in (("orga", "小明"), ("orga", "街道"), ("orgb", "小红")):
                s.add(Asset(id=f"{org}-{name}", org_id=org, type="character", name=name, image_path="x.png"))
            now = datetime.now(UTC)
            for status, cost in (("success", 0.5), ("success", 0.25), ("failed", None)):
                s.add(
                    ApiCall(
                        user_id="u1",
                        project_name="p1",
                        call_type="image",
                        model="m",
                        status=status,
                        started_at=now,
                        cost_amount=cost,
                        currency="CNY",
                        provider="ark",
                    )
                )
            await s.commit()

    asyncio.run(setup())
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(admin, "async_session_factory", maker)
    yield maker
    asyncio.run(engine.dispose())


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="admin", sub="admin", org_id="orgx")
    return TestClient(app)


def test_lists_assets_of_every_org(factory) -> None:
    res = _client().get("/api/v1/saas/admin/assets")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 3
    assert {i["org_id"] for i in body["items"]} == {"orga", "orgb"}

    only_b = _client().get("/api/v1/saas/admin/assets", params={"org_id": "orgb"}).json()
    assert [i["name"] for i in only_b["items"]] == ["小红"]


def test_delete_runs_as_the_owner_org(factory, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str | None] = []

    async def fake_delete(asset_id: str, _t) -> None:
        from saas.adapter.billing_context import get_billing_identity

        identity = get_billing_identity()
        seen.append(identity.org_id if identity else None)

    import server.routers.assets as assets_router

    monkeypatch.setattr(assets_router, "delete_asset", fake_delete)
    client = _client()
    assert client.delete("/api/v1/saas/admin/assets/orgb-小红").status_code == 204
    assert seen == ["orgb"]
    assert client.delete("/api/v1/saas/admin/assets/missing").status_code == 404


def test_user_activity_counts_calls(factory) -> None:
    res = _client().get("/api/v1/saas/admin/users/u1/activity")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["calls"]["total"] == 3
    assert body["calls"]["success"] == 2
    assert body["calls"]["failed"] == 1
    assert body["cost"] == {"CNY": 0.75}
    assert len(body["recent_calls"]) == 3


def test_self_hosted_returns_404(factory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    assert _client().get("/api/v1/saas/admin/assets").status_code == 404
