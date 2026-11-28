"""SaaS: the ArcReel Agent's key, endpoint and model come from the console's Agent config."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lib.db.models.config import SystemSetting
from saas.adapter import agent_config, platform_keys
from saas.adapter import routes_admin_workbench as admin
from server.auth import CurrentUserInfo, get_current_user


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'wb.db'}")

    async def setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: SystemSetting.__table__.create(c))

    asyncio.run(setup())
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("lib.db.async_session_factory", maker)
    platform_keys.clear_platform_key_cache()
    monkeypatch.setattr(platform_keys, "is_saas", lambda: True)

    async def keys():
        return [{"capability": "all", "provider_name": "ark-agent-plan", "secret": "plan-key", "extra": None}]

    monkeypatch.setattr(platform_keys, "control_plane_platform_keys", keys)
    yield maker
    platform_keys.clear_platform_key_cache()
    asyncio.run(engine.dispose())


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="admin", sub="admin", org_id="o")
    return TestClient(app)


def test_not_configured_means_no_override(db) -> None:
    assert asyncio.run(platform_keys.anthropic_platform_env()) == {}


def test_saved_config_drives_the_agent_env(db) -> None:
    res = _client().put(
        "/api/v1/saas/admin/agent",
        json={
            "key_provider": "ark-agent-plan",
            "base_url": "https://ark.cn-beijing.volces.com/api/plan",
            "model": "doubao-seed-evolving",
            "haiku_model": "doubao-seed-2.0-mini",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["config"]["key_provider"] == "ark-agent-plan"
    assert "ark-agent-plan" in body["key_providers"]
    assert any(p["id"] == "ark-agent-plan" for p in body["presets"])

    env = asyncio.run(platform_keys.anthropic_platform_env())
    assert env["ANTHROPIC_API_KEY"] == "plan-key"
    assert env["ANTHROPIC_BASE_URL"] == "https://ark.cn-beijing.volces.com/api/plan"
    assert env["ANTHROPIC_MODEL"] == "doubao-seed-evolving"
    assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "doubao-seed-2.0-mini"
    # Unset tiers fall back to the main model instead of Claude names the endpoint doesn't serve.
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "doubao-seed-evolving"
    assert env["CLAUDE_CODE_SUBAGENT_MODEL"] == "doubao-seed-evolving"


def test_a_disabled_platform_key_gives_no_env(db) -> None:
    asyncio.run(agent_config.save_config({"key_provider": "ark", "base_url": "https://x.example/api", "model": "m"}))
    assert asyncio.run(platform_keys.anthropic_platform_env()) == {}


def test_model_is_required_once_a_key_is_chosen(db) -> None:
    res = _client().put(
        "/api/v1/saas/admin/agent",
        json={"key_provider": "ark-agent-plan", "base_url": "https://ark.cn-beijing.volces.com/api/plan", "model": ""},
    )
    assert res.status_code == 422


def test_token_prices_and_cost() -> None:
    from decimal import Decimal
    from types import SimpleNamespace

    assert agent_config.prices_from_config({"price_input": "4", "price_output": ""}) is None
    prices = agent_config.prices_from_config({"price_input": "4", "price_output": "16", "price_cache_read": ""})
    assert prices is not None
    assert prices.cache_read == Decimal("4")
    row = SimpleNamespace(
        input_tokens=1_000_000,
        output_tokens=500_000,
        cache_read_tokens=0,
        cache_write_5m_tokens=0,
        cache_write_1h_tokens=0,
    )
    assert agent_config.tokens_cost_cny(prices, row) == Decimal("12")


def test_bad_price_is_rejected(db) -> None:
    res = _client().put("/api/v1/saas/admin/agent", json={"price_input": "-1"})
    assert res.status_code == 422


def test_agent_turn_is_charged_by_tokens(db, monkeypatch) -> None:
    from datetime import UTC, datetime
    from decimal import Decimal

    from lib.db.models.api_call import ApiCall
    from saas.adapter import credits_hook
    from saas.adapter.billing_context import BillingIdentity

    async def setup() -> int:
        async with db() as s:
            await s.run_sync(lambda sync: ApiCall.__table__.create(sync.get_bind()))
        async with db() as s:
            row = ApiCall(
                project_name="p",
                call_type="text",
                model="doubao-seed-evolving",
                status="success",
                started_at=datetime.now(UTC),
                provider="anthropic",
                user_id="u",
                input_tokens=200_000,
                output_tokens=50_000,
                cache_read_tokens=1_000_000,
                cost_amount=None,
                currency="USD",
                unpriced_reason="no_entry",
            )
            s.add(row)
            await s.commit()
            return row.id

    call_id = asyncio.run(setup())
    asyncio.run(agent_config.save_config({"price_input": "4", "price_output": "16", "price_cache_read": "0.8"}))
    monkeypatch.setenv("SAAS_CNY_YUAN_TO_CREDITS", "100")
    monkeypatch.setenv("SAAS_COST_TO_CREDITS_MULTIPLIER", "1")
    monkeypatch.setattr(credits_hook, "is_saas", lambda: True)
    settled: dict = {}

    async def fake_settle(**kwargs):
        settled.update(kwargs)
        return {}

    monkeypatch.setattr(credits_hook, "control_plane_internal_settle", fake_settle)
    asyncio.run(
        credits_hook.settle_agent_turn(
            hold_ref="h1",
            call_ids=[call_id],
            session_factory=db,
            identity=BillingIdentity(org_id="o", user_id="u"),
            session_id="s",
        )
    )
    # 0.2M×4 + 0.05M×16 + 1M×0.8 = 2.4 yuan → 240 credits
    assert settled["actual_credits"] == Decimal("240")

    async def reread():
        async with db() as s:
            return await s.get(ApiCall, call_id)

    row = asyncio.run(reread())
    assert Decimal(str(row.cost_amount)) == Decimal("2.4")
    assert row.currency == "CNY"
    assert row.unpriced_reason is None
