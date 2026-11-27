"""SaaS: mirror every project file (uploaded novels, scripts, final cuts, timeline renders, Jianying
drafts, manually uploaded media …) to object storage.

Versioned images, videos and audio already go to object storage as formal objects
(``lib.material.formal_objects`` + ``saas.storage.media_offload``); everything else in a project is
written by many different code paths (source upload, final-cut render, draft export, the Agent's own
Bash edits …). Instead of hooking each writer, a background sweep walks the project directories and
uploads files that are new or changed since the last sweep. Local files stay where they are: the Agent,
ffmpeg renders and exports read them from disk. Object storage holds the durable copy and (next step)
serves downloads through signed URLs.

Object keys are derived from the path only, never from anything stored in the project, so a project
can't point at another tenant's object: ``arcreel-files/org/<org_id>/<project>/<relative path>``.

State lives next to the data root (``.saas_mirror/<org>/<project>.json``) and records, per relative path,
the size and mtime that were uploaded. A file that disappears is deleted remotely after
:data:`MISSING_GRACE` (trash, restore and re-import put it back before that). Follows the same switch as
images: only while "new content target" is object storage and a connection exists. Self-hosted: off.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from saas.adapter.mode import is_saas

logger = logging.getLogger(__name__)

MIRROR_PREFIX = "arcreel-files/"


def _seconds_env(name: str, default: float, minimum: float) -> float:
    """Positive number of seconds from the environment; bad or too small values fall back safely."""
    raw = os.environ.get(name, "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        logger.warning("%s=%r is not a number; using %s", name, raw, default)
        return default
    return max(value, minimum)


# How often the sweep runs, and how long a file must stay unchanged before it is uploaded (so a file
# still being written is not copied half-way). The worst-case delay before a change is in object storage
# is roughly their sum; lower both to shrink what a server crash can lose, at the cost of more listing.
SWEEP_INTERVAL_SECONDS = _seconds_env("SAAS_MIRROR_INTERVAL_SECONDS", 120.0, 15.0)
STABLE_AFTER_SECONDS = _seconds_env("SAAS_MIRROR_STABLE_SECONDS", 30.0, 5.0)
MISSING_GRACE_SECONDS = 7 * 24 * 3600
MAX_BYTES_PER_SWEEP = 2 * 1024**3
MAX_FILES_PER_SWEEP = 500
_SKIP_SUFFIXES = frozenset({".tmp", ".part", ".fetch", ".lock", ".swp"})
_STATE_DIRNAME = ".saas_mirror"


@dataclass(frozen=True)
class MirrorTarget:
    connection_id: int
    bucket: str
    client: Any


def mirror_key(org_id: str, project_name: str, relative_path: str) -> str:
    rel = PurePosixPath(relative_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"invalid relative path: {relative_path!r}")
    return f"{MIRROR_PREFIX}org/{org_id}/{project_name}/{rel.as_posix()}"


def _state_path(data_root: Path, org_id: str, project_name: str) -> Path:
    return Path(data_root) / _STATE_DIRNAME / org_id / f"{project_name}.json"


def _load_state(path: Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(path: Path, state: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _skipped(rel: PurePosixPath) -> bool:
    if any(part.startswith(".") for part in rel.parts) or rel.suffix.lower() in _SKIP_SUFFIXES:
        return True
    return rel.name.endswith(("-wal", "-shm", "-journal"))  # live SQLite side files


def _remote_work_files(project_path: Path) -> set[str]:
    """Paths already saved as formal objects (versioned images / video / audio) — not mirrored twice."""
    try:
        from lib.material.work_files import remote_work_file_digests

        return {PurePosixPath(str(p).replace("\\", "/")).as_posix() for p in remote_work_file_digests(project_path)}
    except Exception:
        logger.warning("mirror: cannot read remote work files project=%s", project_path.name, exc_info=True)
        return set()


def _scan(project_path: Path) -> dict[str, tuple[int, int]]:
    """relative posix path → (size, mtime_ns) of every mirrorable regular file."""
    skip = _remote_work_files(project_path)
    files: dict[str, tuple[int, int]] = {}
    for dirpath, dirnames, filenames in os.walk(project_path):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            path = Path(dirpath) / filename
            rel = PurePosixPath(path.relative_to(project_path).as_posix())
            if _skipped(rel) or rel.as_posix() in skip:
                continue
            try:
                st = path.stat()
            except OSError:
                continue
            if path.is_symlink() or not path.is_file():
                continue
            files[rel.as_posix()] = (st.st_size, st.st_mtime_ns)
    return files


def iter_projects(data_root: Path) -> list[tuple[str, Path]]:
    from lib.infra.data_root_layout import list_project_dirs

    orgs_root = Path(data_root) / "projects" / "org"
    result: list[tuple[str, Path]] = []
    try:
        org_dirs = sorted(p for p in orgs_root.iterdir() if p.is_dir())
    except FileNotFoundError:
        return result
    for org_dir in org_dirs:
        result.extend((org_dir.name, project) for project in list_project_dirs(org_dir))
    return result


@dataclass
class _Budget:
    bytes_left: int = MAX_BYTES_PER_SWEEP
    files_left: int = MAX_FILES_PER_SWEEP

    def take(self, size: int) -> bool:
        if self.files_left <= 0 or (self.bytes_left < size and self.files_left < MAX_FILES_PER_SWEEP):
            return False
        self.files_left -= 1
        self.bytes_left -= size
        return True


def sync_project(
    data_root: Path, org_id: str, project_path: Path | None, project_name: str, target: MirrorTarget,
    budget: _Budget, *, now: float | None = None,
) -> dict[str, int]:
    """Bring one project's remote copy up to date (blocking; run in a worker thread)."""
    now = time.time() if now is None else now
    state_path = _state_path(data_root, org_id, project_name)
    state = _load_state(state_path)
    files = _scan(project_path) if project_path is not None and project_path.is_dir() else {}
    stats = {"uploaded": 0, "deleted": 0, "failed": 0}
    dirty = False
    for rel, (size, mtime_ns) in files.items():
        entry = state.get(rel)
        same_target = entry is not None and (entry.get("connection_id"), entry.get("bucket")) == (
            target.connection_id, target.bucket,
        )
        if same_target and (entry.get("size"), entry.get("mtime_ns")) == (size, mtime_ns):
            if entry.pop("missing_since", None) is not None:
                dirty = True
            continue
        if now - mtime_ns / 1e9 < STABLE_AFTER_SECONDS or not budget.take(size):
            continue
        key = mirror_key(org_id, project_name, rel)
        path = project_path / rel  # type: ignore[operator]
        try:
            content_type = mimetypes.guess_type(rel)[0] or "application/octet-stream"
            target.client.put_file_sync(key, path, content_type=content_type)
            info = target.client.head_sync(key)
            st = path.stat()
        except Exception as exc:  # ObjectStorageError or the file vanished mid-upload
            stats["failed"] += 1
            logger.warning("mirror upload failed project=%s path=%s: %s", project_name, rel, type(exc).__name__)
            continue
        if info.size != size or (st.st_size, st.st_mtime_ns) != (size, mtime_ns):
            continue  # changed while uploading; next sweep uploads the new content
        state[rel] = {
            "size": size, "mtime_ns": mtime_ns, "key": key,
            "connection_id": target.connection_id, "bucket": target.bucket, "uploaded_at": int(now),
        }
        stats["uploaded"] += 1
        dirty = True
    for rel in [r for r in state if r not in files]:
        entry = state[rel]
        if (entry.get("connection_id"), entry.get("bucket")) != (target.connection_id, target.bucket):
            del state[rel]  # belongs to a previous bucket; that bucket is not ours to clean any more
            dirty = True
            continue
        missing_since = entry.setdefault("missing_since", int(now))
        dirty = dirty or missing_since == int(now)
        if now - missing_since < MISSING_GRACE_SECONDS:
            continue
        try:
            target.client.delete_sync(entry["key"])
        except Exception as exc:
            if getattr(exc, "kind", None) != "not_found":
                stats["failed"] += 1
                continue
        del state[rel]
        stats["deleted"] += 1
        dirty = True
    if dirty:
        if state:
            _save_state(state_path, state)
        else:
            with contextlib.suppress(FileNotFoundError):
                state_path.unlink()  # hard-delete: derived -- empty mirror state
    return stats


def mirrored_object(data_root: Path, org_id: str, project_path: Path, relative_path: str) -> dict[str, Any] | None:
    """The mirror entry for ``relative_path`` when the remote copy matches the local file right now."""
    rel = PurePosixPath(relative_path.replace("\\", "/")).as_posix()
    entry = _load_state(_state_path(data_root, org_id, project_path.name)).get(rel)
    if not entry or "missing_since" in entry:
        return None
    try:
        st = (project_path / rel).stat()
    except OSError:
        return None
    if (st.st_size, st.st_mtime_ns) != (entry.get("size"), entry.get("mtime_ns")):
        return None
    if entry.get("key") != mirror_key(org_id, project_path.name, rel):
        return None
    return entry


async def _current_target(session_factory: async_sessionmaker[AsyncSession]) -> MirrorTarget | None:
    from lib.db.repositories.object_storage_repo import ObjectStorageConnectionRepository
    from lib.material.formal_objects import new_content_target
    from lib.object_storage.client import ObjectStorageClient
    from lib.object_storage.connection import config_from_connection

    async with session_factory() as session:
        if await new_content_target(session) != "object_storage":
            return None
        connection = await ObjectStorageConnectionRepository(session).get()
    if connection is None:
        return None
    return MirrorTarget(connection.id, connection.bucket, ObjectStorageClient(config_from_connection(connection)))


def _known_states(data_root: Path) -> list[tuple[str, str]]:
    root = Path(data_root) / _STATE_DIRNAME
    try:
        return [(p.parent.name, p.stem) for p in root.glob("*/*.json")]
    except OSError:
        return []


async def sweep_once(session_factory: async_sessionmaker[AsyncSession], data_root: Path) -> dict[str, int]:
    target = await _current_target(session_factory)
    totals = {"uploaded": 0, "deleted": 0, "failed": 0}
    if target is None:
        return totals
    budget = _Budget()
    projects = await asyncio.to_thread(iter_projects, data_root)
    live = {(org, path.name) for org, path in projects}
    work = [(org, path, path.name) for org, path in projects]
    work += [(org, None, name) for org, name in await asyncio.to_thread(_known_states, data_root) if (org, name) not in live]
    for org, path, name in work:
        try:
            stats = await asyncio.to_thread(sync_project, data_root, org, path, name, target, budget)
        except Exception:
            logger.warning("mirror sweep failed project=%s/%s", org, name, exc_info=True)
            continue
        for k, v in stats.items():
            totals[k] += v
    if any(totals.values()):
        logger.info("project mirror: %s", totals)
    return totals


class ProjectMirror:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], data_root: Path) -> None:
        self._session_factory = session_factory
        self._data_root = Path(data_root)
        self._task: asyncio.Task[None] | None = None

    async def _loop(self) -> None:
        while True:
            try:
                await sweep_once(self._session_factory, self._data_root)
            except Exception:
                logger.warning("project mirror sweep failed; next round", exc_info=True)
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)

    def start(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._loop(), name="saas-project-mirror")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None


def start_project_mirror(session_factory: async_sessionmaker[AsyncSession], data_root: Path) -> ProjectMirror | None:
    if not is_saas():
        return None
    mirror = ProjectMirror(session_factory, data_root)
    mirror.start()
    return mirror
