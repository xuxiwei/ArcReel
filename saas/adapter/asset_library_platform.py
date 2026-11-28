"""SaaS: Ark's private asset library for platform keys.

Upstream binds the asset library to a credential row in the workbench database. In SaaS
the Ark keys come from the control plane (platform keys) and have no such row, so a
generation through them never used the library. This module gives each bindable platform
key a fixed id under ``credential_type="platform"``, so the console can bind it like any
other credential; the binding still checks the key's actual content, so rotating the key
puts the binding back to "needs confirmation".

The console also gets a master switch: off means no call uses the asset library at all
and reference images are sent as image content, exactly as before the library was set up.
Projects are unaffected either way — links live beside the asset images, not in them.

Self-hosted mode: every function here is a no-op.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lib.infra.api_errors import ApiError
from saas.adapter.mode import is_saas

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from lib.asset_library.bindings import InferenceCredential

logger = logging.getLogger(__name__)

PLATFORM_CREDENTIAL_TYPE = "platform"
# Fixed ids: there is one platform key per provider, so the provider is the identity.
PLATFORM_CREDENTIAL_IDS: dict[str, int] = {"ark": 1, "ark-agent-plan": 2}

ENABLED_SETTING_KEY = "saas_asset_library_enabled"


async def _overlays() -> dict[str, dict[str, str]]:
    from saas.adapter.platform_keys import provider_secret_overlays

    try:
        return await provider_secret_overlays()
    except ApiError:
        return {}


async def platform_bindable_credentials() -> list[InferenceCredential]:
    """The platform Ark keys, as bindable credentials (SaaS only)."""
    if not is_saas():
        return []
    from lib.asset_library.bindings import InferenceCredential, effective_endpoint
    from lib.config.registry import PROVIDER_REGISTRY

    overlays = await _overlays()
    credentials: list[InferenceCredential] = []
    for provider, credential_id in PLATFORM_CREDENTIAL_IDS.items():
        overlay = overlays.get(provider) or {}
        api_key = overlay.get("api_key") or ""
        if not api_key:
            continue
        credentials.append(
            InferenceCredential(
                credential_type=PLATFORM_CREDENTIAL_TYPE,
                credential_id=credential_id,
                provider=provider,
                name="平台 Key",
                api_key=api_key,
                endpoint=effective_endpoint(overlay.get("base_url"), PROVIDER_REGISTRY[provider].default_base_url),
            )
        )
    return credentials


async def platform_credential_id(provider_id: str, config: dict[str, str]) -> int | None:
    """The platform credential id when ``config`` carries the platform key for ``provider_id``."""
    if not is_saas() or provider_id not in PLATFORM_CREDENTIAL_IDS:
        return None
    api_key = (config.get("api_key") or "").strip()
    if not api_key:
        return None
    overlay = (await _overlays()).get(provider_id) or {}
    if (overlay.get("api_key") or "").strip() != api_key:
        return None
    return PLATFORM_CREDENTIAL_IDS[provider_id]


def parse_enabled(raw: str | None) -> bool:
    """Unset counts as on: a binding alone already says the admin wants the library."""
    return (raw or "").strip().lower() not in {"false", "0", "off"}


async def asset_library_enabled(session: AsyncSession) -> bool:
    """Whether generations may use the asset library at all (always on when self-hosted)."""
    if not is_saas():
        return True
    from lib.config.repository import SystemSettingRepository

    return parse_enabled(await SystemSettingRepository(session).get(ENABLED_SETTING_KEY, ""))


async def set_asset_library_enabled(session: AsyncSession, enabled: bool) -> None:
    from lib.config.repository import SystemSettingRepository

    await SystemSettingRepository(session).upsert(ENABLED_SETTING_KEY, "true" if enabled else "false")


def fall_back_on_failed_link() -> bool:
    """SaaS: a link whose ingest failed sends the image itself instead of blocking generation.

    Upstream stops the generation so the user sees why the ingest failed. In SaaS the library
    can be switched off or lose assets on the provider side, and projects must keep working,
    so the call goes out as it would without the library.
    """
    return is_saas()
