"""Isolation B path helpers."""

from __future__ import annotations

from pathlib import Path

from saas.adapter.billing_context import BillingIdentity, bind_billing_identity
from saas.isolation.object_keys import apply_tenant_prefix, tenant_object_prefix
from saas.isolation.paths import TenantDataRootLayout, safe_org_segment


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
