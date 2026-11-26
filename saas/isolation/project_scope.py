"""Resolve an org-scoped ProjectManager in SaaS mode."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from lib.infra.app_data_dir import app_data_dir
from lib.infra.data_root_layout import DataRootLayout, is_project_dir
from lib.project.project_manager import ProjectManager
from saas.adapter.billing_context import get_billing_identity
from saas.adapter.mode import is_saas
from saas.isolation.paths import TenantDataRootLayout, safe_org_segment

logger = logging.getLogger(__name__)
_warned_unscoped = False


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
        # Start-up recovery and legacy pre-SaaS data still go through the shared
        # root; log so request paths that lost their identity are visible.
        global _warned_unscoped
        if not _warned_unscoped:
            _warned_unscoped = True
            logger.warning(
                "saas project manager resolved without billing identity; using shared root "
                "(logged once; anonymous public media hits this path)",
                stack_info=True,
            )
        return fallback
    # An identity whose org id is not a safe path segment is a bug or an attack:
    # never fall back to the shared root for it (raises ValueError).
    return _manager_for_org(identity.org_id)


def _unique_org_project_dir(projects_root: Path, project_name: str) -> Path | None:
    """Locate ``projects/org/<org_id>/<project_name>`` when the name matches exactly one org."""
    orgs_root = projects_root / "org"
    try:
        org_dirs = list(orgs_root.iterdir())
    except FileNotFoundError:
        return None
    matches = [candidate for org_dir in org_dirs if is_project_dir(candidate := org_dir / project_name)]
    if len(matches) == 1:
        return matches[0]
    return None


def resolve_public_project_manager(fallback: ProjectManager, project_name: str) -> ProjectManager:
    """Project manager for anonymous public media (``<img>`` / ``<audio>`` have no Bearer).

    Authenticated SaaS requests already bind billing identity → org manager via
    :func:`resolve_project_manager`. Public file routes do not; Isolation B still
    stores projects under ``projects/org/<org_id>/``. Prefer the identity-scoped
    (or flat) path, then fall back to a unique org-nested match so media URLs keep
    working without cookies (ADR 0071).
    """
    manager = resolve_project_manager(fallback)
    name = ProjectManager.normalize_project_name(project_name)
    try:
        manager.get_project_path(name)
        return manager
    except FileNotFoundError:
        if not is_saas():
            raise
    projects_root = DataRootLayout(manager.data_root).projects_dir
    located = _unique_org_project_dir(projects_root, name)
    if located is None:
        raise FileNotFoundError(f"项目 '{name}' 不存在")
    return ProjectManager.for_project_dir(located)


def reset_scoped_managers_for_tests() -> None:
    _manager_for_org.cache_clear()
