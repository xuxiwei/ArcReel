"""SaaS: workbench data the control-plane admin console reads across organisations.

Platform admins only (router dependency ``SAAS_ADMIN_ONLY``). Everything else in the workbench stays
scoped to the caller's organisation; these routes are the deliberate exceptions an operator needs:

- ``GET /saas/admin/assets`` lists the global asset library of every organisation (or one ``org_id``);
- ``DELETE /saas/admin/assets/{id}`` deletes one entry through the normal delete path, run as that
  entry's organisation so links, remote objects and files are released exactly as for its owner;
- ``GET /saas/admin/users/{user_id}/activity`` summarises one user's projects and generation calls.

404 when self-hosted.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import case, func, select

from lib.db import async_session_factory
from lib.db.models.api_call import ApiCall
from lib.db.models.asset import Asset, AssetDerivative
from saas.adapter.mode import is_saas
from server.auth import CurrentUser
from server.i18n import Translator

router = APIRouter(prefix="/saas/admin", tags=["SaaS 管理"])


def _require_saas() -> None:
    if not is_saas():
        raise HTTPException(status_code=404, detail="only available in saas mode")


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


@router.get("/assets")
async def list_all_assets(
    org_id: str | None = None,
    type: str | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    _require_saas()
    conditions = []
    if org_id is not None:
        conditions.append(Asset.org_id == org_id)
    if q:
        conditions.append(Asset.name.icontains(q, autoescape=True))
    async with async_session_factory() as session:
        counts_stmt = select(Asset.type, func.count()).where(*conditions).group_by(Asset.type)
        counts = dict((await session.execute(counts_stmt)).tuples().all())
        stmt = select(Asset).where(*conditions)
        if type:
            stmt = stmt.where(Asset.type == type)
        stmt = stmt.order_by(Asset.updated_at.desc(), Asset.id.desc()).limit(limit).offset(offset)
        assets = list((await session.execute(stmt)).scalars())
        derived: dict[str, int] = {}
        if assets:
            rows = await session.execute(
                select(AssetDerivative.asset_id, func.count())
                .where(AssetDerivative.asset_id.in_([a.id for a in assets]))
                .group_by(AssetDerivative.asset_id)
            )
            derived = dict(rows.tuples().all())
    return {
        "items": [
            {
                "id": a.id,
                "org_id": a.org_id,
                "type": a.type,
                "name": a.name,
                "description": a.description,
                "source_project": a.source_project,
                "has_image": bool(a.image_path or a.image_storage),
                "has_audio": bool(a.audio_path),
                "derivatives": derived.get(a.id, 0),
                "updated_at": _iso(a.updated_at),
            }
            for a in assets
        ],
        "total": counts.get(type, 0) if type else sum(counts.values()),
        "counts": counts,
    }


@router.delete("/assets/{asset_id}", status_code=204)
async def delete_any_asset(asset_id: str, user: CurrentUser, _t: Translator) -> None:
    _require_saas()
    async with async_session_factory() as session:
        owner = await session.scalar(select(Asset.org_id).where(Asset.id == asset_id))
    if owner is None:
        raise HTTPException(status_code=404, detail=_t("asset_not_found", name=asset_id))
    from saas.adapter.billing_context import BillingIdentity, bind_billing_identity
    from server.routers.assets import delete_asset

    # The normal path is scoped to the bound organisation; run it as the owner's.
    with bind_billing_identity(BillingIdentity(user_id=user.id, org_id=owner)):
        await delete_asset(asset_id, _t)


def _project_titles(org_id: str, limit: int) -> tuple[int, list[dict[str, Any]]]:
    from saas.isolation.project_scope import _manager_for_org

    manager = _manager_for_org(org_id)
    names = sorted(manager.list_projects())
    projects: list[dict[str, Any]] = []
    for name in names[:limit]:
        title = None
        try:
            title = (manager.load_project(name) or {}).get("title")
        except Exception:  # a broken project.json must not hide the rest
            title = None
        projects.append({"name": name, "title": title})
    return len(names), projects


@router.get("/users/{user_id}/activity")
async def user_activity(
    user_id: str,
    org_id: str | None = None,
    project_limit: Annotated[int, Query(ge=0, le=200)] = 50,
) -> dict[str, Any]:
    _require_saas()
    import asyncio

    project_count, projects = (0, [])
    if org_id:
        try:
            project_count, projects = await asyncio.to_thread(_project_titles, org_id, project_limit)
        except ValueError as exc:  # unsafe org id
            raise HTTPException(status_code=400, detail="invalid org_id") from exc

    def _count(status: str) -> Callable[..., Any]:
        return func.sum(case((ApiCall.status == status, 1), else_=0))

    async with async_session_factory() as session:
        totals = (
            await session.execute(
                select(
                    func.count(),
                    _count("success"),
                    _count("failed"),
                    func.max(ApiCall.started_at),
                ).where(ApiCall.user_id == user_id)
            )
        ).one()
        cost_rows = await session.execute(
            select(ApiCall.currency, func.sum(ApiCall.cost_amount))
            .where(ApiCall.user_id == user_id, ApiCall.cost_amount.is_not(None))
            .group_by(ApiCall.currency)
        )
        by_type = await session.execute(
            select(ApiCall.call_type, func.count()).where(ApiCall.user_id == user_id).group_by(ApiCall.call_type)
        )
        recent = list(
            (
                await session.execute(
                    select(ApiCall).where(ApiCall.user_id == user_id).order_by(ApiCall.started_at.desc()).limit(10)
                )
            ).scalars()
        )
    return {
        "project_count": project_count,
        "projects": projects,
        "calls": {
            "total": int(totals[0] or 0),
            "success": int(totals[1] or 0),
            "failed": int(totals[2] or 0),
            "last_started_at": _iso(totals[3]),
            "by_media_type": {k: int(v) for k, v in by_type.tuples().all()},
        },
        "cost": {currency: round(float(amount or 0), 6) for currency, amount in cost_rows.tuples().all()},
        "recent_calls": [
            {
                "id": c.id,
                "project_name": c.project_name,
                "media_type": c.call_type,
                "provider": c.provider,
                "model": c.model,
                "status": c.status,
                "cost_amount": c.cost_amount,
                "currency": c.currency,
                "started_at": _iso(c.started_at),
            }
            for c in recent
        ],
    }
