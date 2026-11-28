"""Fetch platform provider secrets from the control plane and overlay configs."""

from __future__ import annotations

import logging
import time
from typing import Any

from lib.infra.api_errors import ApiError
from saas.adapter.control_plane_client import ControlPlaneError, control_plane_platform_keys
from saas.adapter.mode import is_saas

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 30.0
_cache: tuple[float, dict[str, dict[str, str]]] | None = None

# Maps control-plane capability → preferred when multiple rows share a provider_name.
_CAPABILITY_PRIORITY = ("agent", "text", "image", "video", "tts")


def _row_to_overlay(row: dict[str, Any]) -> dict[str, str]:
    overlay: dict[str, str] = {}
    secret = row.get("secret")
    if isinstance(secret, str) and secret:
        overlay["api_key"] = secret
    extra = row.get("extra")
    if isinstance(extra, dict):
        for key, value in extra.items():
            if isinstance(key, str) and isinstance(value, str) and value:
                overlay[key] = value
    return overlay


async def provider_secret_overlays() -> dict[str, dict[str, str]]:
    """provider_id → secret field overlays (api_key / access_key / …)."""
    global _cache
    if not is_saas():
        return {}
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < _CACHE_TTL_SEC:
        return _cache[1]
    try:
        rows = await control_plane_platform_keys()
    except ControlPlaneError as exc:
        logger.error("platform keys fetch failed: %s", exc.detail)
        if _cache is not None:
            return _cache[1]
        # Fail closed: an empty overlay would let the resolver fall back to the
        # instance's local credential table (instance-owner or tenant-uploaded keys).
        raise ApiError("platform_keys_unavailable", status_code=503) from exc

    by_provider: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        name = row.get("provider_name")
        if not isinstance(name, str) or not name:
            continue
        by_provider.setdefault(name, []).append(row)

    result: dict[str, dict[str, str]] = {}
    for provider_id, items in by_provider.items():
        items_sorted = sorted(
            items,
            key=lambda r: (
                _CAPABILITY_PRIORITY.index(r["capability"])
                if isinstance(r.get("capability"), str) and r["capability"] in _CAPABILITY_PRIORITY
                else len(_CAPABILITY_PRIORITY)
            ),
        )
        overlay: dict[str, str] = {}
        # Apply lowest priority first so the highest-priority capability wins
        # any field both rows set (``update`` keeps the last writer).
        for item in reversed(items_sorted):
            overlay.update(_row_to_overlay(item))
        if overlay:
            result[provider_id] = overlay

    _cache = (now, result)
    return result


async def platform_ready_providers() -> frozenset[str]:
    """Built-in providers an active platform key fully configures (SaaS only).

    The workbench marks a provider "ready" from its own credential table, which SaaS
    tenants never fill (BYOK is off). Without this, a provider the platform pays for
    shows as unconfigured and none of its models can be picked. A provider counts
    when the platform overlay carries every key the registry requires.

    Listing pages must keep working while the control plane is down, so a failed
    fetch here yields "none" instead of an error; generation still fails closed.
    """
    if not is_saas():
        return frozenset()
    try:
        overlays = await provider_secret_overlays()
    except ApiError:
        return frozenset()
    from lib.config.registry import PROVIDER_REGISTRY

    return frozenset(
        name
        for name, overlay in overlays.items()
        if name in PROVIDER_REGISTRY and all(overlay.get(key) for key in PROVIDER_REGISTRY[name].required_keys)
    )


async def inject_platform_keys(config: dict[str, str], provider_id: str) -> dict[str, str]:
    """Overlay platform secrets onto a provider config (SaaS only; platform wins)."""
    if not is_saas():
        return config
    overlays = await provider_secret_overlays()
    secrets = overlays.get(provider_id)
    if not secrets:
        return config
    config.update(secrets)
    return config


async def inject_platform_keys_bulk(configs: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    if not is_saas():
        return configs
    overlays = await provider_secret_overlays()
    for provider_id, secrets in overlays.items():
        configs.setdefault(provider_id, {}).update(secrets)
    return configs


async def anthropic_platform_env() -> dict[str, str]:
    """ANTHROPIC_* env overrides from capability=agent / anthropic-like providers."""
    if not is_saas():
        return {}
    overlays = await provider_secret_overlays()
    from saas.adapter.agent_config import configured_agent_env

    # The console's Agent config (platform key + endpoint + model) wins when set.
    configured = await configured_agent_env(overlays)
    if configured:
        return configured
    for key in ("anthropic", "claude", "agent"):
        secrets = overlays.get(key)
        if secrets and secrets.get("api_key"):
            env = {"ANTHROPIC_API_KEY": secrets["api_key"]}
            if secrets.get("base_url"):
                env["ANTHROPIC_BASE_URL"] = secrets["base_url"]
            return env
    # capability=agent with provider_name matching any overlay that set api_key for agent rows
    # already folded into overlays by provider_name; nothing else to do.
    return {}


def clear_platform_key_cache() -> None:
    global _cache
    _cache = None
