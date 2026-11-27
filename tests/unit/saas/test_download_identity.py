"""SaaS: download_token links bind the issuer's org before the route's services resolve projects."""

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from saas.adapter.billing_context import BillingIdentity, get_billing_identity, set_billing_identity
from saas.isolation.download_identity import bind_download_identity


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setattr("server.auth.get_token_secret", lambda: "test-secret-test-secret-test-secret!")


def _issue(project: str, identity: BillingIdentity | None) -> str:
    from server.auth import create_download_token

    token = set_billing_identity(identity)
    try:
        return create_download_token("alice", project)
    finally:
        from saas.adapter.billing_context import reset_billing_identity

        reset_billing_identity(token)


def _app() -> FastAPI:
    router = APIRouter()

    def service():  # resolved after the router dependency, like ArchiveServiceDep
        identity = get_billing_identity()
        return identity.org_id if identity else None

    @router.get("/projects/{name}/export")
    async def export(name: str, download_token: str, org=Depends(service)):
        return {"org": org}

    app = FastAPI()
    app.include_router(router, prefix="/api/v1", dependencies=[Depends(bind_download_identity)])
    return app


def test_token_carries_org_and_binds_it() -> None:
    import jwt

    token = _issue("demo", BillingIdentity(user_id="u1", org_id="orga"))
    claims = jwt.decode(token, "test-secret-test-secret-test-secret!", algorithms=["HS256"])
    assert (claims["org"], claims["uid"]) == ("orga", "u1")
    response = TestClient(_app()).get("/api/v1/projects/demo/export", params={"download_token": token})
    assert response.json() == {"org": "orga"}


def test_token_for_another_project_binds_nothing() -> None:
    token = _issue("other", BillingIdentity(user_id="u1", org_id="orga"))
    response = TestClient(_app()).get("/api/v1/projects/demo/export", params={"download_token": token})
    assert response.json() == {"org": None}


def test_self_hosted_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    import jwt

    token = _issue("demo", BillingIdentity(user_id="u1", org_id="orga"))
    assert "org" not in jwt.decode(token, "test-secret-test-secret-test-secret!", algorithms=["HS256"])
    response = TestClient(_app()).get("/api/v1/projects/demo/export", params={"download_token": token})
    assert response.json() == {"org": None}
