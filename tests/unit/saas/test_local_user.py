"""Unit tests for local SaaS user provisioning."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lib.db.models.user import User
from saas.adapter.local_user import clear_local_saas_user_cache, ensure_local_saas_user, local_username


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_local_saas_user_inserts_once(
    db_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_local_saas_user_cache()
    # ensure_local_saas_user imports async_session_factory from lib.db inside the function
    import lib.db as lib_db

    monkeypatch.setattr(lib_db, "async_session_factory", db_factory)

    await ensure_local_saas_user("saas-user-1", username="alice")
    await ensure_local_saas_user("saas-user-1", username="alice")

    async with db_factory() as session:
        rows = (await session.execute(select(User).where(User.id == "saas-user-1"))).scalars().all()
    assert len(rows) == 1
    assert rows[0].username == "alice"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_local_saas_user_fallback_username(
    db_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_local_saas_user_cache()
    import lib.db as lib_db

    monkeypatch.setattr(lib_db, "async_session_factory", db_factory)

    await ensure_local_saas_user("saas-user-2")
    async with db_factory() as session:
        row = await session.get(User, "saas-user-2")
    assert row is not None
    assert row.username == "saas:saas-user-2"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_local_saas_user_lowercases_username(
    db_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_local_saas_user_cache()
    import lib.db as lib_db

    monkeypatch.setattr(lib_db, "async_session_factory", db_factory)

    await ensure_local_saas_user("saas-user-3", username="  Alice ")
    async with db_factory() as session:
        row = await session.get(User, "saas-user-3")
    assert row is not None
    assert row.username == "alice"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_username_hides_placeholder(
    db_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_local_saas_user_cache()
    import lib.db as lib_db

    monkeypatch.setattr(lib_db, "async_session_factory", db_factory)

    await ensure_local_saas_user("saas-user-4", username="bob")
    await ensure_local_saas_user("saas-user-5")
    assert await local_username("saas-user-4") == "bob"
    assert await local_username("saas-user-5") is None
    assert await local_username("missing-user") is None
