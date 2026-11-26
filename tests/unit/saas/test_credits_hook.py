"""Unit tests for SaaS credit conversion and hold helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from saas.adapter import credits_hook
from saas.adapter.billing_context import BillingIdentity
from saas.adapter.credits_hook import (
    CreditConversionError,
    _legacy_call_ids,
    cost_to_credits,
    credit_call_id,
    hold_estimate,
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "CONTROL_PLANE_URL",
        "SAAS_CNY_YUAN_TO_CREDITS",
        "SAAS_COST_TO_CREDITS_MULTIPLIER",
        "SAAS_FX_USD_TO_CNY",
        "SAAS_HOLD_ESTIMATE_CREDITS",
        "SAAS_HOLD_ESTIMATE_VIDEO",
    ):
        monkeypatch.delenv(name, raising=False)
    credits_hook.clear_credit_config_cache()
    yield
    credits_hook.clear_credit_config_cache()


def test_credit_call_id_is_unique_across_id_reuse() -> None:
    """Same local id, different start time (SQLite id reuse after reset) → different key."""
    first = credit_call_id(42, datetime(2026, 11, 1, 8, 0, 0, 123456))
    reused = credit_call_id(42, datetime(2026, 11, 26, 9, 30, 0, 1))
    assert first == "api_call:42:20261101080000123456"
    assert first != reused


def test_credit_call_id_normalizes_timezone() -> None:
    naive_utc = datetime(2026, 11, 26, 1, 0, 0)
    aware = datetime(2026, 11, 26, 9, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    assert credit_call_id(7, naive_utc) == credit_call_id(7, aware) == credit_call_id(7, naive_utc.replace(tzinfo=UTC))


def test_legacy_call_ids_cover_pre_upgrade_holds() -> None:
    assert _legacy_call_ids(42, None) == ["api_call:42"]
    identity = BillingIdentity(user_id="u1", org_id="org-9")
    assert _legacy_call_ids(42, identity) == ["org:org-9:api_call:42", "api_call:42"]


@pytest.mark.asyncio
async def test_cost_to_credits_converts_currency_then_rate_then_markup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAAS_FX_USD_TO_CNY", "7.2")
    monkeypatch.setenv("SAAS_CNY_YUAN_TO_CREDITS", "10")
    monkeypatch.setenv("SAAS_COST_TO_CREDITS_MULTIPLIER", "1.5")
    # $1 → ¥7.2 → 72 credits → ×1.5 markup
    assert await cost_to_credits(1, "USD") == Decimal("108.000000")
    # CNY needs no fx rate
    assert await cost_to_credits(Decimal("2"), "CNY") == Decimal("30.000000")
    assert await cost_to_credits(0, "USD") == Decimal("0")
    # Missing currency means CNY on this platform.
    assert await cost_to_credits(Decimal("1"), None) == Decimal("15.000000")
    assert await cost_to_credits(-5, "USD") == Decimal("0")


@pytest.mark.asyncio
async def test_cost_to_credits_refuses_to_guess(monkeypatch: pytest.MonkeyPatch) -> None:
    """No fx rate and no control plane → error, never a silent 1:1 default."""
    monkeypatch.setenv("SAAS_CNY_YUAN_TO_CREDITS", "10")
    monkeypatch.setenv("SAAS_COST_TO_CREDITS_MULTIPLIER", "1")
    with pytest.raises(CreditConversionError):
        await cost_to_credits(1, "USD")
    with pytest.raises(CreditConversionError):
        await cost_to_credits(1, "US$")


@pytest.mark.asyncio
async def test_config_keeps_last_good_value_when_control_plane_drops(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    async def _config(key: str) -> str:
        calls["n"] += 1
        if calls["n"] > 1:
            raise credits_hook.ControlPlaneError(503, "down")
        return "7"

    monkeypatch.setattr(credits_hook, "control_plane_internal_config", _config)
    monkeypatch.setattr(credits_hook, "_CONFIG_TTL_SEC", 0.0)
    assert await credits_hook._config_decimal("fx_usd_to_cny", "SAAS_FX_USD_TO_CNY") == Decimal("7")
    assert await credits_hook._config_decimal("fx_usd_to_cny", "SAAS_FX_USD_TO_CNY") == Decimal("7")


def test_hold_estimate_scales_video_by_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    assert hold_estimate("image") == Decimal("10.000000")
    assert hold_estimate("video", 5) == Decimal("10.000000")
    assert hold_estimate("video", 12) == Decimal("30.000000")
    monkeypatch.setenv("SAAS_HOLD_ESTIMATE_VIDEO", "4")
    assert hold_estimate("video", 10) == Decimal("8.000000")
    monkeypatch.setenv("SAAS_HOLD_ESTIMATE_CREDITS", "not-a-number")
    assert hold_estimate("image") == Decimal("10.000000")
