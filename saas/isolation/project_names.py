"""SaaS: a project name is unique across all organisations.

Projects live under ``projects/org/<org_id>/<name>``, but several instance-wide records are keyed
by the bare project name: object-storage references (``object_storage_formal_object_ref.project_name``),
deleted-project tombstones, and the anonymous media route that locates a project by a unique name.
If two organisations had a project with the same name, recomputing one project's object references
would drop the other's and the object-storage sweep could delete objects that are still in use.

Every place that claims a project directory name (create, restore from deleted projects, archive
import) already holds the data-root-wide ``project_names_lock``; while holding it they also ask
:func:`name_taken_elsewhere`. Self-hosted mode is unchanged.
"""

from __future__ import annotations

from pathlib import Path

from lib.infra.data_root_layout import DataRootLayout
from saas.adapter.mode import is_saas


def _taken(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def name_taken_elsewhere(layout: DataRootLayout, name: str) -> bool:
    """``name`` is used by a project of another organisation (or the flat legacy root)."""
    if not is_saas():
        return False
    flat = DataRootLayout(layout.root)
    own = Path(layout.projects_dir) / name
    candidates = [flat.projects_dir / name]
    orgs_root = flat.projects_dir / "org"
    try:
        candidates.extend(org_dir / name for org_dir in orgs_root.iterdir() if org_dir.is_dir())
    except FileNotFoundError:
        pass
    return any(candidate != own and _taken(candidate) for candidate in candidates)


def duplicate_project_names(root: Path) -> dict[str, list[str]]:
    """Names used by more than one organisation — run once on existing data (see patches/project-name-unique.md)."""
    orgs_root = DataRootLayout(root).projects_dir / "org"
    seen: dict[str, list[str]] = {}
    try:
        org_dirs = sorted(p for p in orgs_root.iterdir() if p.is_dir())
    except FileNotFoundError:
        return {}
    for org_dir in org_dirs:
        for child in org_dir.iterdir():
            if child.is_dir() and (child / "project.json").is_file():
                seen.setdefault(child.name, []).append(org_dir.name)
    return {name: orgs for name, orgs in seen.items() if len(orgs) > 1}


if __name__ == "__main__":  # python -m saas.isolation.project_names
    from lib.infra.app_data_dir import app_data_dir

    duplicates = duplicate_project_names(app_data_dir())
    print("no duplicate project names" if not duplicates else duplicates)
