"""SaaS: media already in object storage is downloaded from it directly (302 to a signed URL).

Serving videos through the workbench costs its bandwidth twice; once a file is in object storage the
browser can fetch it from there. ``serve_project_file`` asks :func:`object_storage_redirect` after the
viewer is authorised (``saas.isolation.media_access``). A file qualifies when it is

- the work file of a remote content version (versioned image / video / audio, stored as a formal
  object), or
- a project file mirrored by ``saas.storage.project_mirror`` whose remote copy matches the local file,

and the object sits on the current connection. Everything else, thumbnails (``?w=``) included, is
served locally as before. The signed URL lives :data:`PRESIGN_SECONDS`; the redirect itself may be
cached privately for a few minutes.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Any

from saas.adapter.mode import is_saas

logger = logging.getLogger(__name__)

PRESIGN_SECONDS = 3600
REDIRECT_CACHE_SECONDS = 300
_CONNECTION_TTL = 30.0
_connection_cache: tuple[float, Any] | None = None
_FORMAL_CACHE: dict[str, tuple[object, dict[str, Any]]] = {}
_FORMAL_GUARD = threading.Lock()


def clear_caches() -> None:
    global _connection_cache
    _connection_cache = None
    with _FORMAL_GUARD:
        _FORMAL_CACHE.clear()


async def _current_connection() -> Any:
    """(id, bucket, client) of the current connection, cached briefly; ``None`` without one."""
    global _connection_cache
    now = time.monotonic()
    if _connection_cache is not None and now - _connection_cache[0] < _CONNECTION_TTL:
        return _connection_cache[1]
    from lib.db import async_session_factory
    from lib.db.repositories.object_storage_repo import ObjectStorageConnectionRepository
    from lib.object_storage.client import ObjectStorageClient
    from lib.object_storage.connection import config_from_connection

    async with async_session_factory() as session:
        conn = await ObjectStorageConnectionRepository(session).get()
    value = None if conn is None else (conn.id, conn.bucket, ObjectStorageClient(config_from_connection(conn)))
    _connection_cache = (now, value)
    return value


def _formal_locator(project_dir: Path, rel: str) -> Any:
    """ObjectLocator of the remote content version whose work file is ``rel``, if any."""
    from lib.material.work_files import locked_remote_work_files, remote_work_file_digests

    digests = remote_work_file_digests(project_dir)
    if rel not in digests:
        return None
    key = str(project_dir)
    with _FORMAL_GUARD:
        cached = _FORMAL_CACHE.get(key)
    if cached is None or cached[0] is not digests:
        mapping = {item.path: item.stored for item in locked_remote_work_files(project_dir)}
        with _FORMAL_GUARD:
            _FORMAL_CACHE[key] = (digests, mapping)  # keeps ``digests`` alive, so ``is`` stays meaningful
    else:
        mapping = cached[1]
    return mapping.get(rel)


def _mirror_locator(project_dir: Path, rel: str, org_id: str) -> tuple[int, str, str] | None:
    from saas.storage.project_mirror import mirrored_object

    data_root = project_dir.parents[3]  # <root>/projects/org/<org>/<project>
    entry = mirrored_object(data_root, org_id, project_dir, rel)
    if entry is None:
        return None
    return int(entry["connection_id"]), str(entry["bucket"]), str(entry["key"])


async def object_storage_redirect(project_dir: Path, relative_parts: tuple[str, ...], org_id: str | None) -> str | None:
    if not is_saas() or org_id is None or not relative_parts:
        return None
    try:
        connection = await _current_connection()
        if connection is None:
            return None
        conn_id, bucket, client = connection
        rel = "/".join(relative_parts)
        stored = await asyncio.to_thread(_formal_locator, project_dir, rel)
        if stored is not None:
            target = (stored.connection_id, stored.bucket, stored.key)
        else:
            target = await asyncio.to_thread(_mirror_locator, project_dir, rel, org_id)
        if target is None or (target[0], target[1]) != (conn_id, bucket):
            return None
        return await client.presign_get(target[2], expires_seconds=PRESIGN_SECONDS)
    except Exception:
        logger.warning("object storage redirect unavailable; serving locally", exc_info=True)
        return None
