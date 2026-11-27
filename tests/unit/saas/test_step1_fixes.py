"""SaaS small fixes: org-nested maintenance, connection guard, media cookie on login / logout."""

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from saas.isolation import maintenance_scope
from saas.isolation.connection_guard import ensure_no_active_tasks
from saas.isolation.media_access import MEDIA_COOKIE, clear_media_cookie, decode_media_cookie, issue_media_cookie


@pytest.fixture(autouse=True)
def saas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setattr("server.auth.get_token_secret", lambda: "test-secret")


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalars(self):
        return iter(self.value)


class _Session:
    def __init__(self, value):
        self.value = value

    async def execute(self, _stmt):
        return _Result(self.value)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


async def test_connection_change_blocked_while_tasks_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from lib.infra.api_errors import ConflictError

    with pytest.raises(ConflictError):
        await ensure_no_active_tasks(_Session(2))
    await ensure_no_active_tasks(_Session(0))
    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    await ensure_no_active_tasks(_Session(5))


def test_login_sets_and_logout_clears_the_media_cookie() -> None:
    app = FastAPI()

    @app.post("/api/v1/auth/token")
    def login(request: Request, response: Response):
        issue_media_cookie(request, response, org_id="orga", user_id="u1")
        return {"ok": True}

    @app.post("/api/v1/auth/logout")
    def logout():
        result = Response(status_code=204)
        clear_media_cookie(result)
        return result

    client = TestClient(app)
    client.post("/api/v1/auth/token")
    assert decode_media_cookie(client.cookies.get(MEDIA_COOKIE))["o"] == "orga"
    cleared = client.post("/api/v1/auth/logout")
    assert MEDIA_COOKIE in cleared.headers["set-cookie"] and "Max-Age=0" in cleared.headers["set-cookie"]


async def test_maintenance_runs_per_org(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for org in ("orga", "orgb"):
        (tmp_path / "projects" / "org" / org).mkdir(parents=True)
    retained, cleaned = [], []

    async def fake_retain(projects_dir, deleted_dir, session_factory=None, **_):
        retained.append((Path(projects_dir).name, deleted_dir))
        return 0

    async def fake_cleanup(projects_dir, *, min_idle, session_factory=None):
        cleaned.append(Path(projects_dir).name)

    monkeypatch.setattr("lib.material.formal_objects.retain_formal_objects", fake_retain)
    monkeypatch.setattr("lib.material.work_files.cleanup_work_cache", fake_cleanup)
    await maintenance_scope.retain_all(tmp_path, lambda: _Session([]))
    await maintenance_scope.cleanup_all(tmp_path, lambda: _Session([]), min_idle=timedelta(hours=1))
    assert retained == [("orga", None), ("orgb", None)]
    assert cleaned == ["orga", "orgb"]


async def test_expired_tombstone_kept_while_any_org_still_has_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from datetime import UTC, datetime

    holder = "demo-tombstone"
    monkeypatch.setattr(
        "lib.db.repositories.project_records.parse_deleted_project_name",
        lambda name: ("demo", datetime(2000, 1, 1, tzinfo=UTC)) if name == holder else None,
    )
    (tmp_path / "deleted_projects" / "org" / "orga" / holder).mkdir(parents=True)
    released: list[str] = []

    async def fake_release(h, session_factory=None):
        released.append(h)
        return 1

    async def fake_retain(*_a, **_k):
        return 0

    monkeypatch.setattr("lib.material.formal_objects.retain_formal_objects", fake_retain)
    monkeypatch.setattr("lib.material.formal_objects.release_holder", fake_release)
    await maintenance_scope.retain_all(tmp_path, lambda: _Session([holder]))
    assert released == []
    (tmp_path / "deleted_projects" / "org" / "orga" / holder).rmdir()
    await maintenance_scope.retain_all(tmp_path, lambda: _Session([holder]))
    assert released == [holder]


def test_upstream_files_call_the_saas_hooks() -> None:
    root = Path(__file__).resolve().parents[3]
    assert "await self._saas_hourly()" in (root / "lib/material/maintenance.py").read_text(encoding="utf-8")
    storage = (root / "server/routers/object_storage.py").read_text(encoding="utf-8")
    assert storage.count("await ensure_no_active_tasks(session)") == 2
    auth = (root / "server/routers/auth.py").read_text(encoding="utf-8")
    assert auth.count("_issue_media_cookie(request, response, claims)") == 2
    assert '@public_router.post("/auth/logout"' in auth
