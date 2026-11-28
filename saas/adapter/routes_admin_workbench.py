"""SaaS: workbench data the control-plane admin console reads across organisations.

Platform admins only (router dependency ``SAAS_ADMIN_ONLY``). Everything else in the workbench stays
scoped to the caller's organisation; these routes are the deliberate exceptions an operator needs:

- ``GET /saas/admin/assets`` lists the global asset library of every organisation (or one ``org_id``);
- ``DELETE /saas/admin/assets/{id}`` deletes one entry through the normal delete path, run as that
  entry's organisation so links, remote objects and files are released exactly as for its owner;
- ``GET /saas/admin/users/{user_id}/activity`` summarises one user's projects and generation calls;
- ``GET|PUT /saas/admin/agent`` reads and saves the ArcReel Agent's platform key, endpoint and model
  (:mod:`saas.adapter.agent_config`); ``POST /saas/admin/agent/test`` sends it one tiny request.

404 when self-hosted.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
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


# ---- ArcReel Agent model (console: 系统 → Agent 模型) ----


class AgentConfigBody(BaseModel):
    key_provider: str = ""
    base_url: str = ""
    model: str = ""
    haiku_model: str = ""
    sonnet_model: str = ""
    opus_model: str = ""
    subagent_model: str = ""
    price_input: str = ""
    price_output: str = ""
    price_cache_read: str = ""


async def _agent_payload() -> dict[str, Any]:
    from lib.agent.agent_provider_catalog import list_presets
    from saas.adapter import agent_config
    from saas.adapter.platform_keys import provider_secret_overlays

    try:
        overlays = await provider_secret_overlays()
    except Exception:  # control plane down: still show the saved config
        overlays = {}
    return {
        "config": await agent_config.load_config(),
        "key_providers": sorted(name for name, o in overlays.items() if o.get("api_key")),
        "presets": [
            {
                "id": p.id,
                "display_name": p.display_name,
                "base_url": p.messages_url,
                "default_model": p.default_model,
                "suggested_models": list(p.suggested_models),
            }
            for p in list_presets()
        ],
    }


@router.get("/agent")
async def get_agent_config() -> dict[str, Any]:
    _require_saas()
    return await _agent_payload()


@router.put("/agent")
async def put_agent_config(body: AgentConfigBody) -> dict[str, Any]:
    _require_saas()
    from saas.adapter import agent_config

    values = body.model_dump()
    values = {k: v.strip() for k, v in values.items()}
    if values["key_provider"]:
        if not values["base_url"].startswith(("https://", "http://")):
            raise HTTPException(status_code=422, detail="接口地址要以 https:// 开头")
        if not values["model"]:
            raise HTTPException(status_code=422, detail="请填写模型")
    for field in agent_config.PRICE_FIELDS:
        try:
            agent_config.parse_price(values[field])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="价格要填不小于 0 的数字") from exc
    await agent_config.save_config(values)
    return await _agent_payload()


@router.post("/agent/test")
async def test_agent_config() -> dict[str, Any]:
    """One tiny Messages request with the saved config; the reply says whether the key, endpoint and model work."""
    _require_saas()
    import httpx

    from saas.adapter import agent_config
    from saas.adapter.platform_keys import clear_platform_key_cache, provider_secret_overlays

    clear_platform_key_cache()
    env = await agent_config.configured_agent_env(await provider_secret_overlays())
    if not env:
        return {"ok": False, "message": "还没配置完整：要选平台 Key、填接口地址和模型，并且那个平台 Key 处于启用状态"}
    url = env["ANTHROPIC_BASE_URL"].rstrip("/") + "/v1/messages"
    headers = {
        "x-api-key": env["ANTHROPIC_API_KEY"],
        "authorization": f"Bearer {env['ANTHROPIC_API_KEY']}",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {"model": env["ANTHROPIC_MODEL"], "max_tokens": 8, "messages": [{"role": "user", "content": "hi"}]}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        return {"ok": False, "message": f"连不上 {url}：{type(exc).__name__}"}
    if res.status_code == 200:
        return {"ok": True, "message": f"通过：{env['ANTHROPIC_MODEL']} 正常回复"}
    try:
        detail = res.json().get("error", {}).get("message") or res.text
    except ValueError:
        detail = res.text
    return {"ok": False, "message": f"HTTP {res.status_code}：{str(detail)[:300]}"}
