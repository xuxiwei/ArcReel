"""Keep SaaS secrets out of the process environment after start-up.

``.env`` is loaded into ``os.environ`` at start-up, and every child process the
workbench starts (ffmpeg, the Agent CLI, skill scripts) inherits that environment;
a same-user process can read a child's ``/proc/<pid>/environ``. Once start-up is
done, :func:`seal_secret_env` moves the secret-looking variables (the SaaS patterns
in ``saas.isolation.agent_sandbox``: control-plane token/URL/keys, ``DATABASE_URL``,
passwords, other ``*SECRET*``) into this module, so no later child sees them.

SaaS code reads those settings through :func:`get` (process env first, so tests and
start-up still work, then the sealed copy). The two upstream readers that run after
start-up are handled here: ``DATABASE_URL`` via a one-line fallback in
``lib/db/engine.get_database_url``; ``AUTH_TOKEN_SECRET`` and the ``AUTH_PASSWORD``
hash by priming ``server.auth``'s caches before the variables are removed.
"""

from __future__ import annotations

import logging
import os
from collections.abc import MutableMapping

logger = logging.getLogger(__name__)

_vault: dict[str, str] = {}


def get(name: str, default: str = "") -> str:
    """A setting from the process env, else from the sealed copy."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    return _vault.get(name, default)


def is_sealed(name: str) -> bool:
    return name in _vault


def seal_secret_env(environ: MutableMapping[str, str] | None = None) -> list[str]:
    """Move secret variables out of ``environ`` (default ``os.environ``). Returns their names."""
    from saas.isolation.agent_sandbox import saas_secret_env_keys

    env = os.environ if environ is None else environ
    names = saas_secret_env_keys(env)
    if environ is None:
        import server.auth as workbench_auth

        token_secret = env.get("AUTH_TOKEN_SECRET", "").strip()
        if token_secret:
            # get_token_secret() prefers the env var and falls back to this cache; keep it identical.
            workbench_auth._cached_token_secret = token_secret
        if env.get("AUTH_PASSWORD"):
            # The password hash is computed lazily from the env var; compute it now, or a later
            # check_credentials() would hash "" and accept an empty password.
            workbench_auth._get_password_hash()
    for name in names:
        value = env.pop(name, None)
        if value is not None:
            _vault[name] = value.strip()
    if names:
        logger.info("sealed %d secret settings out of the process environment: %s", len(names), ", ".join(names))
    return names


def reset_for_tests() -> None:
    _vault.clear()
