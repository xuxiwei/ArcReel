"""SaaS: assigning pre-SaaS assets to an organisation; mirror timing from the environment."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lib.db.models.asset import Asset, AssetDerivative
from saas.isolation.assign_legacy_assets import apply_assignment, plan_assignment


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Asset.metadata.create_all(c, tables=[Asset.__table__, AssetDerivative.__table__]))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_legacy_assets_move_without_overwriting(session_factory) -> None:
    async with session_factory() as s:
        s.add_all(
            [
                Asset(id="l1", org_id="", type="character", name="小明"),
                Asset(id="l2", org_id="", type="scene", name="街道"),
                Asset(id="o1", org_id="orga", type="scene", name="街道"),
            ]
        )
        await s.commit()
    async with session_factory() as s:
        plan = await plan_assignment(s, "orga")
        assert [m[0] for m in plan.move] == ["l1"]
        assert [c[0] for c in plan.conflicts] == ["l2"]
        assert await apply_assignment(s, "orga", plan) == 1
    async with session_factory() as s:
        assert (await s.get(Asset, "l1")).org_id == "orga"
        assert (await s.get(Asset, "l2")).org_id == ""


def test_mirror_timing_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from saas.storage.project_mirror import _seconds_env

    monkeypatch.delenv("X_MIRROR", raising=False)
    assert _seconds_env("X_MIRROR", 120.0, 15.0) == 120.0
    monkeypatch.setenv("X_MIRROR", "30")
    assert _seconds_env("X_MIRROR", 120.0, 15.0) == 30.0
    monkeypatch.setenv("X_MIRROR", "1")
    assert _seconds_env("X_MIRROR", 120.0, 15.0) == 15.0
    monkeypatch.setenv("X_MIRROR", "soon")
    assert _seconds_env("X_MIRROR", 120.0, 15.0) == 120.0
