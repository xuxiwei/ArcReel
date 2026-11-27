"""SaaS: project names are unique across organisations (object-storage references are keyed by name)."""

import json
from pathlib import Path

import pytest

from lib.project.project_manager import ProjectManager
from saas.isolation.paths import TenantDataRootLayout
from saas.isolation.project_names import duplicate_project_names, name_taken_elsewhere


def _project(root: Path, org: str, name: str) -> Path:
    path = root / "projects" / "org" / org / name
    path.mkdir(parents=True)
    (path / "project.json").write_text(json.dumps({"content_mode": "narration"}), encoding="utf-8")
    return path


def _manager(root: Path, org: str) -> ProjectManager:
    layout = TenantDataRootLayout(root=root, org_id=org)
    manager = ProjectManager(root)
    manager.layout = layout
    manager.projects_dir = layout.projects_dir
    manager.projects_dir.mkdir(parents=True, exist_ok=True)
    return manager


@pytest.fixture(autouse=True)
def saas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")


def test_name_of_another_org_is_taken(tmp_path: Path) -> None:
    _project(tmp_path, "orga", "demo")
    assert name_taken_elsewhere(TenantDataRootLayout(root=tmp_path, org_id="orgb"), "demo")
    assert not name_taken_elsewhere(TenantDataRootLayout(root=tmp_path, org_id="orga"), "demo")
    assert not name_taken_elsewhere(TenantDataRootLayout(root=tmp_path, org_id="orgb"), "other")


def test_self_hosted_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    _project(tmp_path, "orga", "demo")
    assert not name_taken_elsewhere(TenantDataRootLayout(root=tmp_path, org_id="orgb"), "demo")


def test_create_refuses_a_name_used_by_another_org(tmp_path: Path) -> None:
    _project(tmp_path, "orga", "demo")
    manager = _manager(tmp_path, "orgb")
    with pytest.raises(FileExistsError):
        manager.create_project("demo")
    assert not (manager.projects_dir / "demo").exists()
    assert manager.create_project("demo-2").is_dir()


def test_generated_names_skip_other_orgs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _project(tmp_path, "orga", "proj-aaaaaaaa")
    tokens = iter(["aaaaaaaa", "bbbbbbbb"])
    monkeypatch.setattr("lib.project.project_manager.secrets.token_hex", lambda n: next(tokens))
    assert _manager(tmp_path, "orgb").generate_project_name(None) == "proj-bbbbbbbb"


def test_duplicate_report(tmp_path: Path) -> None:
    _project(tmp_path, "orga", "demo")
    _project(tmp_path, "orgb", "demo")
    _project(tmp_path, "orgb", "solo")
    assert duplicate_project_names(tmp_path) == {"demo": ["orga", "orgb"]}
