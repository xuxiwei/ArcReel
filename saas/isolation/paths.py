"""Org-scoped project / trash directories for SaaS isolation B."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from lib.infra.data_root_layout import DataRootLayout

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")


def safe_org_segment(org_id: str) -> str:
    """Filesystem segment for an org id (UUID / slug)."""
    value = (org_id or "").strip()
    if not value or not _SAFE_SEGMENT.fullmatch(value):
        raise ValueError(f"invalid org_id for path isolation: {org_id!r}")
    return value


@dataclass(frozen=True)
class TenantDataRootLayout(DataRootLayout):
    """Data root with projects/ and deleted_projects/ nested under org/<org_id>/."""

    org_id: str = ""

    def __post_init__(self) -> None:
        if self.org_id:
            object.__setattr__(self, "org_id", safe_org_segment(self.org_id))

    @property
    def projects_dir(self) -> Path:
        if not self.org_id:
            return super().projects_dir
        return super().projects_dir / "org" / self.org_id

    @property
    def deleted_projects_dir(self) -> Path:
        if not self.org_id:
            return super().deleted_projects_dir
        return super().deleted_projects_dir / "org" / self.org_id


def tenant_layout_for(org_id: str, *, root: Path | None = None) -> TenantDataRootLayout:
    base = DataRootLayout.current() if root is None else DataRootLayout(root)
    return TenantDataRootLayout(root=base.root, org_id=org_id)
