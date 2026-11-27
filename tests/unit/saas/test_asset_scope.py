"""SaaS: the global asset library is per organisation."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lib.db.models.asset import Asset, AssetDerivative
from lib.db.repositories.asset_repo import AssetRepository
from saas.adapter.billing_context import BillingIdentity, reset_billing_identity, set_billing_identity
from saas.isolation.asset_scope import AssetOrgUnavailable, asset_file_visible, current_asset_org, org_for_create


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Asset.metadata.create_all(c, tables=[Asset.__table__, AssetDerivative.__table__]))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _as(org: str | None):
    return set_billing_identity(BillingIdentity(user_id="u", org_id=org) if org else None)


@pytest.fixture
def saas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")


def test_org_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    assert current_asset_org() == ""
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    token = _as(None)
    try:
        assert current_asset_org() is None
        with pytest.raises(AssetOrgUnavailable):
            org_for_create()
    finally:
        reset_billing_identity(token)


async def test_orgs_do_not_see_each_other(saas, session_factory) -> None:
    for org in ("orga", "orgb"):
        token = _as(org)
        try:
            async with session_factory() as s:
                await AssetRepository(s).create(type="character", name="小明", image_path=f"global_assets/character/{org}.png")
                await s.commit()
        finally:
            reset_billing_identity(token)

    token = _as("orga")
    try:
        async with session_factory() as s:
            repo = AssetRepository(s)
            rows = await repo.list(type=None, q=None)
            assert [r.image_path for r in rows] == ["global_assets/character/orga.png"]
            assert await repo.count_by_type(q=None) == {"character": 1}
            mine = await repo.get_by_type_name("character", "小明")
            assert mine is not None and mine.org_id == "orga"
            async with session_factory() as other:
                theirs = (await other.execute(Asset.__table__.select().where(Asset.org_id == "orgb"))).first()
            assert await repo.get_by_id(theirs.id) is None
            assert await asset_file_visible(s, "global_assets/character/orga.png", "orga")
            assert not await asset_file_visible(s, "global_assets/character/orgb.png", "orga")
    finally:
        reset_billing_identity(token)


async def test_no_identity_sees_nothing(saas, session_factory) -> None:
    token = _as("orga")
    try:
        async with session_factory() as s:
            await AssetRepository(s).create(type="scene", name="街道")
            await s.commit()
    finally:
        reset_billing_identity(token)
    token = _as(None)
    try:
        async with session_factory() as s:
            assert await AssetRepository(s).list(type=None, q=None) == []
    finally:
        reset_billing_identity(token)


def test_media_route_checks_ownership() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[3] / "server/routers/files.py").read_text(encoding="utf-8")
    assert "await asset_file_visible(session" in source
