"""Isolation B path helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.infra.data_root_layout import PROJECT_FILENAME
from lib.project.project_manager import ProjectManager
from saas.adapter.billing_context import BillingIdentity, bind_billing_identity
from saas.isolation.object_keys import apply_tenant_prefix, tenant_object_prefix
from saas.isolation.paths import TenantDataRootLayout, safe_org_segment
from saas.isolation.project_scope import resolve_public_project_manager


def test_tenant_layout_nests_org() -> None:
    layout = TenantDataRootLayout(root=Path("/data"), org_id="org-1")
    assert layout.projects_dir == Path("/data/projects/org/org-1")
    assert layout.deleted_projects_dir == Path("/data/deleted_projects/org/org-1")


def test_safe_org_rejects_traversal() -> None:
    try:
        safe_org_segment("../x")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_object_prefix_saas(monkeypatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    with bind_billing_identity(BillingIdentity(user_id="user-1", org_id="org-1")):
        assert tenant_object_prefix() == "org/org-1/user/user-1/"
        assert apply_tenant_prefix("sha256/ab/cd.png") == "org/org-1/user/user-1/sha256/ab/cd.png"


def test_object_prefix_self_hosted(monkeypatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    with bind_billing_identity(BillingIdentity(user_id="user-1", org_id="org-1")):
        assert tenant_object_prefix() == ""
        assert apply_tenant_prefix("sha256/ab/cd.png") == "sha256/ab/cd.png"


def test_resolve_public_project_manager_finds_org_nested(tmp_path: Path, monkeypatch) -> None:
    """Anonymous public media must still resolve Isolation B org paths."""
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")

    project_dir = tmp_path / "projects" / "org" / "org-9" / "proj-abc"
    project_dir.mkdir(parents=True)
    (project_dir / PROJECT_FILENAME).write_text("{}", encoding="utf-8")

    fallback = ProjectManager(tmp_path)
    with pytest.raises(FileNotFoundError):
        fallback.get_project_path("proj-abc")

    resolved = resolve_public_project_manager(fallback, "proj-abc")
    assert resolved.get_project_path("proj-abc") == project_dir.resolve()


def test_resolve_public_project_manager_ambiguous_orgs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    for org in ("org-a", "org-b"):
        project_dir = tmp_path / "projects" / "org" / org / "proj-dup"
        project_dir.mkdir(parents=True)
        (project_dir / PROJECT_FILENAME).write_text("{}", encoding="utf-8")

    fallback = ProjectManager(tmp_path)
    with pytest.raises(FileNotFoundError):
        resolve_public_project_manager(fallback, "proj-dup")
