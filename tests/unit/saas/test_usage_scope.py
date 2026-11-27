"""SaaS: members read their own usage records, platform admins read all."""

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from lib.db.models.api_call import ApiCall
from saas.isolation import admin_guard
from saas.isolation.admin_guard import SAAS_USAGE_SCOPE
from saas.isolation.usage_scope import current_usage_user, scope_usage_query, set_usage_user
from server.auth import EMBEDDED_AGENT_SUB, CurrentUserInfo, get_current_user


@pytest.fixture(autouse=True)
def saas(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")

    async def fake_fetch(token: str) -> bool:
        return token == "admin"

    monkeypatch.setattr(admin_guard, "_fetch_is_admin", fake_fetch)
    admin_guard.clear_admin_cache()
    yield
    set_usage_user(None)


def _app(sub: str = "u1") -> FastAPI:
    router = APIRouter()

    @router.get("/usage/records")
    async def records():
        return {"scope": current_usage_user()}

    app = FastAPI()
    app.include_router(router, prefix="/api/v1", dependencies=[Depends(SAAS_USAGE_SCOPE)])
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="u1", sub=sub, role="member", org_id="o1")
    return app


def _get(client: TestClient, token: str):
    return client.get("/api/v1/usage/records", headers={"Authorization": f"Bearer {token}"})


def test_member_is_scoped_admin_is_not() -> None:
    client = TestClient(_app())
    assert _get(client, "member").json() == {"scope": "u1"}
    assert _get(client, "admin").json() == {"scope": None}


def test_embedded_agent_cannot_read_usage() -> None:
    assert _get(TestClient(_app(sub=EMBEDDED_AGENT_SUB)), "admin").status_code == 403


def test_self_hosted_unscoped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    assert _get(TestClient(_app()), "member").json() == {"scope": None}


def test_query_filter_adds_user_clause() -> None:
    stmt = select(ApiCall.id)
    assert scope_usage_query(stmt, ApiCall) is stmt
    set_usage_user("u1")
    scoped = str(scope_usage_query(stmt, ApiCall).compile(compile_kwargs={"literal_binds": True}))
    assert "api_calls.user_id = 'u1'" in scoped


def test_usage_repository_uses_the_scope() -> None:
    from lib.db.repositories.usage_repo import UsageRepository

    set_usage_user("u1")
    repo = UsageRepository(session=None)  # type: ignore[arg-type]
    scoped = str(repo._scope_query(select(ApiCall.id), ApiCall).compile(compile_kwargs={"literal_binds": True}))
    assert "user_id = 'u1'" in scoped
