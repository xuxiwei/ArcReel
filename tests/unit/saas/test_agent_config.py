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
