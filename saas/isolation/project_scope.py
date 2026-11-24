"""Resolve an org-scoped ProjectManager in SaaS mode."""

from __future__ import annotations

from functools import lru_cache

from lib.infra.app_data_dir import app_data_dir
from lib.project.project_manager import ProjectManager
from saas.adapter.billing_context import get_billing_identity
from saas.adapter.mode import is_saas
from saas.isolation.paths import TenantDataRootLayout, safe_org_segment


@lru_cache(maxsize=64)
def _manager_for_org(org_id: str) -> ProjectManager:
    layout = TenantDataRootLayout(root=app_data_dir(), org_id=safe_org_segment(org_id))
    manager = ProjectManager(layout.root)
    manager.layout = layout
    manager.projects_dir = layout.projects_dir
    manager.projects_dir.mkdir(parents=True, exist_ok=True)
    layout.deleted_projects_dir.mkdir(parents=True, exist_ok=True)
    return manager


def resolve_project_manager(fallback: ProjectManager) -> ProjectManager:
    """SaaS + billing identity → org-scoped manager; otherwise upstream singleton."""
    if not is_saas():
        return fallback
    identity = get_billing_identity()
    if identity is None:
        return fallback
    try:
        return _manager_for_org(identity.org_id)
    except ValueError:
        return fallback


def reset_scoped_managers_for_tests() -> None:
    _manager_for_org.cache_clear()
