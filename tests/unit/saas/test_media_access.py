"""SaaS: media routes need the viewer's org cookie; stored media redirects to object storage."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient

from saas.isolation import media_access as ma
from saas.storage import media_redirect as mr


@pytest.fixture(autouse=True)
def saas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setattr("server.auth.get_token_secret", lambda: "test-secret")
    mr.clear_caches()


def test_cookie_round_trip_tamper_and_expiry() -> None:
    value = ma.encode_media_cookie("orga", "u1", now=1000)
    assert ma.decode_media_cookie(value, now=1001)["o"] == "orga"
    body, sig = value.split(".")
    assert ma.decode_media_cookie(f"{body}.{sig[:-2]}AA", now=1001) is None
    assert ma.decode_media_cookie(value, now=1000 + ma.TTL_SECONDS + 1) is None
    assert ma.decode_media_cookie("garbage", now=1001) is None


def _app(user) -> FastAPI:
    app = FastAPI()

    def current(request: Request, response: Response):
        ma.refresh_media_cookie(request, response, user)
        return user

    @app.get("/api/v1/me")
    def me(_=Depends(current)):
        return {"ok": True}

    @app.get("/api/v1/files/x")
    def media(request: Request):
        return {"org": ma.media_org(request)}

    return app


def test_authenticated_calls_issue_the_cookie_once_and_media_needs_it() -> None:
    client = TestClient(_app(SimpleNamespace(id="u1", sub="u1", org_id="orga")))
    assert client.get("/api/v1/files/x").status_code == 401
    first = client.get("/api/v1/me")
    assert ma.MEDIA_COOKIE in first.headers.get("set-cookie", "")
    assert "httponly" in first.headers["set-cookie"].lower()
    assert "set-cookie" not in client.get("/api/v1/me").headers  # still fresh
    assert client.get("/api/v1/files/x").json() == {"org": "orga"}


def test_embedded_agent_gets_no_cookie() -> None:
    from server.auth import EMBEDDED_AGENT_SUB

    client = TestClient(_app(SimpleNamespace(id="u1", sub=EMBEDDED_AGENT_SUB, org_id="orga")))
    assert "set-cookie" not in client.get("/api/v1/me").headers


def test_self_hosted_media_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    client = TestClient(_app(SimpleNamespace(id="u1", sub="u1", org_id="orga")))
    assert client.get("/api/v1/files/x").json() == {"org": None}
    assert "set-cookie" not in client.get("/api/v1/me").headers


def test_files_router_uses_the_cookie_and_redirect() -> None:
    source = (Path(__file__).resolve().parents[3] / "server/routers/files.py").read_text(encoding="utf-8")
    assert "viewer_org = media_org(request)" in source
    assert "object_storage_redirect(project_dir, relative_parts, viewer_org)" in source
    assert "media_org(request)  # SaaS PATCH: signed-in viewers only" in source


class _Client:
    async def presign_get(self, key, *, expires_seconds):
        return f"https://oss.example/{key}?e={expires_seconds}"


async def test_redirect_for_formal_objects_on_the_current_connection(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    async def conn():
        return (7, "media", _Client())

    monkeypatch.setattr(mr, "_current_connection", conn)
    locator = SimpleNamespace(connection_id=7, bucket="media", key="arcreel-materials/org/a/x.mp4")
    monkeypatch.setattr(mr, "_formal_locator", lambda d, rel: locator if rel == "videos/scene_1.mp4" else None)
    monkeypatch.setattr(mr, "_mirror_locator", lambda d, rel, org: None)
    url = await mr.object_storage_redirect(tmp_path, ("videos", "scene_1.mp4"), "orga")
    assert url == f"https://oss.example/arcreel-materials/org/a/x.mp4?e={mr.PRESIGN_SECONDS}"
    assert await mr.object_storage_redirect(tmp_path, ("videos", "other.mp4"), "orga") is None

    locator.bucket = "old-bucket"
    assert await mr.object_storage_redirect(tmp_path, ("videos", "scene_1.mp4"), "orga") is None


async def test_redirect_for_mirrored_files(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    import os
    import time

    from saas.storage import project_mirror as pm

    project = tmp_path / "projects" / "org" / "orga" / "demo"
    (project / "renders").mkdir(parents=True)
    (project / "project.json").write_text("{}", encoding="utf-8")
    final = project / "renders" / "final.mp4"
    final.write_bytes(b"film")
    old = time.time() - 120
    os.utime(final, (old, old))

    class Mirror:
        def put_file_sync(self, key, path, *, content_type=None):
            self.size = Path(path).stat().st_size

        def head_sync(self, key):
            return SimpleNamespace(size=self.size)

    pm.sync_project(tmp_path, "orga", project, "demo", pm.MirrorTarget(7, "media", Mirror()), pm._Budget())

    async def conn():
        return (7, "media", _Client())

    monkeypatch.setattr(mr, "_current_connection", conn)
    monkeypatch.setattr(mr, "_formal_locator", lambda d, rel: None)
    url = await mr.object_storage_redirect(project, ("renders", "final.mp4"), "orga")
    assert url.startswith("https://oss.example/arcreel-files/org/orga/demo/renders/final.mp4")
    final.write_bytes(b"new cut")  # local changed, mirror not yet → served locally
    assert await mr.object_storage_redirect(project, ("renders", "final.mp4"), "orga") is None


async def test_no_redirect_when_self_hosted(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    assert await mr.object_storage_redirect(tmp_path, ("videos", "a.mp4"), "orga") is None
