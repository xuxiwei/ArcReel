"""SaaS hardening for the Agent's Bash sandbox (multi-tenant).

Upstream's access policy assumes one trusted user per install: the built-in
Read/Write tools are fenced by hooks, but sandboxed Bash only gets a deny-list
(workbench ``.env`` and the data root's system entries). With many tenants on
one host that leaves three gaps, closed here and wired in by two small hooks in
``server/agent_runtime/agent_access_policy.py`` and ``options_assembler.py``:

1. Secret env names upstream's patterns miss (``CONTROL_PLANE_JWT_SECRET``,
   ``CONTROL_PLANE_INTERNAL_TOKEN``, ``DATABASE_URL``, ``AUTH_PASSWORD`` ...):
   blanked in the CLI subprocess env and unset in every Bash command.
2. Other tenants' projects: Bash may read anything under ``projects/`` that is
   not on the path to the session's own project. Every sibling along that path
   is added to ``denyRead`` (other orgs, other projects, legacy flat projects).
3. Host paths outside the data root (control-plane code and ``.env``, backups,
   other sites on the box, other sessions' SDK transcripts): ``denyRead`` from
   ``ARCREEL_AGENT_DENY_READ`` plus the SDK projects dir siblings.

The sandbox is compiled once per session, so directories created after the
session started (a brand-new tenant's first project) are not covered until the
next session; the OS-level split (control plane under its own user, backups
root-only) does not depend on this list.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from pathlib import Path

# Name fragments (upper-cased match) that mark a variable as secret in SaaS.
SAAS_SECRET_ENV_PATTERNS: tuple[str, ...] = (
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "PRIVATE_KEY",
    "DATABASE_URL",
    "_DSN",
    "CONTROL_PLANE_",
)
# Needed inside the sandbox: skill scripts call the workbench API with it, and it
# is a short-lived token scoped to the session's own user.
_KEEP_ENV: frozenset[str] = frozenset({"ARCREEL_API_TOKEN", "ARCREEL_API_BASE"})

DENY_READ_ENV = "ARCREEL_AGENT_DENY_READ"


def saas_secret_env_keys(environ: Mapping[str, str] | None = None) -> list[str]:
    """Names in ``environ`` that look secret under the SaaS patterns."""
    env = os.environ if environ is None else environ
    keys = []
    for name in env:
        if name in _KEEP_ENV:
            continue
        upper = name.upper()
        if any(pattern in upper for pattern in SAAS_SECRET_ENV_PATTERNS):
            keys.append(name)
    return sorted(keys)


def blank_secret_env(agent_env: dict[str, str], environ: Mapping[str, str] | None = None) -> list[str]:
    """Override secret parent-process variables with "" in the CLI subprocess env.

    The SDK starts the CLI with ``{**os.environ, **options.env}``; blanking here keeps
    the values out of the CLI process (and so out of every Bash child and of
    ``/proc/<cli>/environ``). Keys the caller already set on purpose are left alone.
    """
    blanked = []
    for key in saas_secret_env_keys(environ):
        if key not in agent_env:
            agent_env[key] = ""
            blanked.append(key)
    return blanked


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return path


def sibling_paths_along(root: Path, target: Path) -> list[Path]:
    """Every entry under ``root`` that is not on the path from ``root`` to ``target``.

    Denying all of them leaves ``target`` (and its own subtree) readable while hiding
    everything beside it at every level. Returns [] when ``target`` is not under ``root``.
    """
    root_r, target_r = _resolve(root), _resolve(target)
    try:
        parts = target_r.relative_to(root_r).parts
    except ValueError:
        return []
    out: list[Path] = []
    current = root_r
    for part in parts:
        try:
            entries = sorted(current.iterdir())
        except OSError:
            break
        out.extend(entry for entry in entries if entry.name != part)
        current = current / part
    return out


def configured_deny_read(environ: Mapping[str, str] | None = None) -> list[Path]:
    """Existing paths from ``ARCREEL_AGENT_DENY_READ`` (``os.pathsep``-separated)."""
    env = os.environ if environ is None else environ
    raw = env.get(DENY_READ_ENV, "")
    paths = []
    for item in raw.split(os.pathsep):
        item = item.strip()
        if not item:
            continue
        path = Path(item).expanduser()
        if path.exists():
            paths.append(_resolve(path))
    return paths


def saas_extra_deny_read(
    *,
    projects_dir: Path,
    project_cwd: Path,
    sdk_projects_dir: Path | None,
    sdk_project_dir_name: str | None,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Extra ``filesystem.denyRead`` entries for a SaaS Agent session."""
    deny: list[Path] = []
    deny.extend(sibling_paths_along(projects_dir, project_cwd))
    if sdk_projects_dir is not None and sdk_projects_dir.is_dir():
        if sdk_project_dir_name:
            deny.extend(sibling_paths_along(sdk_projects_dir, sdk_projects_dir / sdk_project_dir_name))
        else:
            deny.extend(_resolve(entry) for entry in sdk_projects_dir.iterdir())
        history = sdk_projects_dir.parent / "history.jsonl"
        if history.exists():
            deny.append(_resolve(history))
    deny.extend(configured_deny_read(environ))
    return _dedupe(str(path) for path in deny)


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
