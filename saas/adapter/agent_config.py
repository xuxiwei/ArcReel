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

Billing: Agent turns are charged by tokens. The model names of subscription endpoints (e.g.
``doubao-seed-evolving``) are not in the price catalog, which would charge every turn a flat estimate,
so the admin sets the Agent's token prices here (CNY per million tokens). When set, they price every
Agent turn: input, output and cache-read tokens × price, then the usual CNY → credits conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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
    "price_input": "saas_agent_price_input",
    "price_output": "saas_agent_price_output",
    "price_cache_read": "saas_agent_price_cache_read",
}
PRICE_FIELDS = ("price_input", "price_output", "price_cache_read")
_PER_TOKENS = Decimal(1_000_000)


@dataclass(frozen=True)
class TokenPrices:
    """CNY per million tokens."""

    input: Decimal
    output: Decimal
    cache_read: Decimal


def parse_price(raw: str) -> Decimal | None:
    """A price field: empty → None; otherwise a finite number ≥ 0, else ValueError."""
    text = (raw or "").strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(text) from exc
    if not value.is_finite() or value < 0:
        raise ValueError(text)
    return value


def prices_from_config(config: dict[str, str]) -> TokenPrices | None:
    """Prices are on when input and output are both set; cache reads default to the input price."""
    try:
        price_in = parse_price(config.get("price_input", ""))
        price_out = parse_price(config.get("price_output", ""))
        price_cache = parse_price(config.get("price_cache_read", ""))
    except ValueError:
        return None
    if price_in is None or price_out is None:
        return None
    return TokenPrices(input=price_in, output=price_out, cache_read=price_in if price_cache is None else price_cache)


def tokens_cost_cny(prices: TokenPrices, row: Any) -> Decimal:
    """One ``api_calls`` row of an Agent turn, in CNY. Cache writes are billed as input."""

    def n(name: str) -> Decimal:
        return Decimal(int(getattr(row, name, 0) or 0))

    total = (
        n("input_tokens") * prices.input
        + n("output_tokens") * prices.output
        + n("cache_read_tokens") * prices.cache_read
        + (n("cache_write_5m_tokens") + n("cache_write_1h_tokens")) * prices.input
    )
    return total / _PER_TOKENS


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


async def load_token_prices() -> TokenPrices | None:
    try:
        return prices_from_config(await load_config())
    except Exception:  # settings unreadable: fall back to catalog prices / the estimate
        return None


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
