"""SaaS: run the hourly material maintenance over org-nested projects.

``lib.material.maintenance`` scans the flat ``projects/`` directory. SaaS projects live in
``projects/org/<org_id>/<name>`` (names are unique across orgs, see ``project_names``), so the flat
scan finds none of them: object references were never re-computed hourly and idle image work files
were never evicted. :func:`retain_all` / :func:`cleanup_all` run the upstream routines once per
organisation directory.

Expired deleted-project tombstones are released only when the tombstone directory exists in no
organisation's ``deleted_projects`` (the upstream check looks in the flat directory only).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


def _org_dirs(root: Path) -> list[Path]:
    try:
        return sorted(p for p in root.iterdir() if p.is_dir())
    except FileNotFoundError:
        return []


async def retain_all(data_root: Path, session_factory: async_sessionmaker[AsyncSession]) -> int:
    from lib.db.base import utc_now
    from lib.db.models.object_storage import FormalObjectRef
    from lib.db.repositories.project_records import parse_deleted_project_name
    from lib.material.formal_objects import _HELD_STATES, _TOMBSTONE_GRACE, release_holder, retain_formal_objects
    from lib.project.project_trash import RETENTION

    root = Path(data_root)
    deleted = 0
    for org_dir in await asyncio.to_thread(_org_dirs, root / "projects" / "org"):
        try:
            deleted += await retain_formal_objects(org_dir, None, session_factory=session_factory)
        except Exception:
            logger.warning("retain formal objects failed org=%s", org_dir.name, exc_info=True)
    deleted_roots = [root / "deleted_projects", *await asyncio.to_thread(_org_dirs, root / "deleted_projects" / "org")]
    cutoff = utc_now() - RETENTION - _TOMBSTONE_GRACE
    async with session_factory() as session:
        holders = (
            await session.execute(
                select(FormalObjectRef.project_name).where(FormalObjectRef.state.in_(_HELD_STATES)).distinct()
            )
        ).scalars()
        expired = [h for h in holders if (parsed := parse_deleted_project_name(h)) is not None and parsed[1] <= cutoff]
    for holder in expired:
        exists = await asyncio.to_thread(lambda h=holder: any((d / h).exists() for d in deleted_roots))
        if not exists:
            deleted += await release_holder(holder, session_factory)
    return deleted


async def cleanup_all(
    data_root: Path, session_factory: async_sessionmaker[AsyncSession], *, min_idle: timedelta
) -> None:
    from lib.material.work_files import cleanup_work_cache

    for org_dir in await asyncio.to_thread(_org_dirs, Path(data_root) / "projects" / "org"):
        try:
            await cleanup_work_cache(org_dir, min_idle=min_idle, session_factory=session_factory)
        except Exception:
            logger.warning("work cache cleanup failed org=%s", org_dir.name, exc_info=True)
