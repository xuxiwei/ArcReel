"""SaaS: the ArcReel Agent's model, set by the platform admin in the control-plane console.

The Agent speaks the Anthropic Messages API. In SaaS the platform pays for it, so its key comes from a
platform key (the control plane's encrypted store) and the admin picks only which one, plus the endpoint
and the model. Saved in workbench system settings:

- ``saas_agent_key_provider`` — platform key to use (e.g. ``ark-agent-plan``; the same subscription key
  that serves images and video also serves the Agent through the Anthropic-compatible ``/api/plan``);
- the upstream ``anthropic_base_url`` / ``anthropic_model`` / tier settings for endpoint and models.

When configured, :func:`configured_agent_env` gives the complete ANTHROPIC_* environment, so a leftover
local Agent credential can't mix its endpoint or models with the platform key. Empty tier models fall
back to the main model: Claude Code otherwise asks for Claude model names the endpoint doesn't serve.
"""

from __future__ import annotations

from typing import Any

KEY_PROVIDER_SETTING = "saas_agent_key_provider"

# API field -> workbench system setting
SETTING_KEYS: dict[str, str] = {
    "key_provider": KEY_PROVIDER_SETTING,
    "base_url": "anthropic_base_url",
    "model": "anthropic_model",
    "haiku_model": "anthropic_default_haiku_model",
    "sonnet_model": "anthropic_default_sonnet_model",
    "opus_model": "anthropic_default_opus_model",
    "subagent_model": "claude_code_subagent_model",
}


def config_from_settings(settings: dict[str, str]) -> dict[str, str]:
    return {field: (settings.get(key) or "").strip() for field, key in SETTING_KEYS.items()}


def env_from_config(config: dict[str, str], api_key: str) -> dict[str, str]:
    model = config["model"]
    return {
        "ANTHROPIC_API_KEY": api_key,
        "ANTHROPIC_BASE_URL": config["base_url"],
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": config["haiku_model"] or model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": config["sonnet_model"] or model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": config["opus_model"] or model,
        "CLAUDE_CODE_SUBAGENT_MODEL": config["subagent_model"] or model,
    }


async def load_config() -> dict[str, str]:
    from lib.config.repository import SystemSettingRepository
    from lib.db import async_session_factory

    async with async_session_factory() as session:
        return config_from_settings(await SystemSettingRepository(session).get_all())


async def save_config(values: dict[str, Any]) -> dict[str, str]:
    from lib.config.repository import SystemSettingRepository
    from lib.db import async_session_factory

    async with async_session_factory() as session:
        repo = SystemSettingRepository(session)
        for field, key in SETTING_KEYS.items():
            if field in values:
                await repo.upsert(key, str(values[field] or "").strip())
        await session.commit()
        return config_from_settings(await repo.get_all())


async def configured_agent_env(overlays: dict[str, dict[str, str]]) -> dict[str, str]:
    """Full ANTHROPIC_* env from the console's Agent config; empty when not configured or not usable."""
    config = await load_config()
    provider = config["key_provider"]
    if not provider or not config["base_url"] or not config["model"]:
        return {}
    api_key = (overlays.get(provider) or {}).get("api_key", "")
    if not api_key:
        return {}
    return env_from_config(config, api_key)
