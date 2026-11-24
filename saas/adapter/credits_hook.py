"""SaaS credit hold / settle / release beside the workbench cost ledger."""

from __future__ import annotations

import logging
import os
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from lib.infra.api_errors import ApiError

from saas.adapter.billing_context import get_billing_identity
from saas.adapter.control_plane_client import (
    ControlPlaneError,
    control_plane_internal_config,
    control_plane_internal_hold,
    control_plane_internal_release,
    control_plane_internal_settle,
)
from saas.adapter.mode import is_saas

logger = logging.getLogger(__name__)

_QUANT = Decimal("0.000001")
_DEFAULT_HOLD = Decimal("10")
_multiplier_cache: tuple[float, Decimal] | None = None
_MULTIPLIER_TTL_SEC = 60.0


def credit_call_id(api_call_id: int) -> str:
    return f"api_call:{api_call_id}"


def _default_hold_estimate() -> Decimal:
    raw = os.environ.get("SAAS_HOLD_ESTIMATE_CREDITS", "").strip() or str(_DEFAULT_HOLD)
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return _DEFAULT_HOLD
    return value if value > 0 else _DEFAULT_HOLD


async def _cost_to_credits_multiplier() -> Decimal:
    global _multiplier_cache
    now = time.monotonic()
    if _multiplier_cache is not None and now - _multiplier_cache[0] < _MULTIPLIER_TTL_SEC:
        return _multiplier_cache[1]
    env = os.environ.get("SAAS_COST_TO_CREDITS_MULTIPLIER", "").strip()
    if env:
        try:
            value = Decimal(env)
            if value > 0:
                _multiplier_cache = (now, value)
                return value
        except InvalidOperation:
            pass
    try:
        raw = await control_plane_internal_config("cost_to_credits_multiplier")
        value = Decimal(raw)
        if value <= 0:
            value = Decimal("1.0")
    except (ControlPlaneError, InvalidOperation):
        value = Decimal("1.0")
    _multiplier_cache = (now, value)
    return value


def cost_to_credits(cost_amount: float | Decimal | None, *, multiplier: Decimal) -> Decimal:
    if cost_amount is None:
        return Decimal("0")
    amount = Decimal(str(cost_amount))
    if amount < 0:
        amount = Decimal("0")
    return (amount * multiplier).quantize(_QUANT, rounding=ROUND_HALF_UP)


async def hold_for_api_call(
    *,
    api_call_id: int,
    task_id: str | None,
    purpose: str | None,
    meta: dict[str, Any] | None = None,
) -> str | None:
    """Hold credits before a billable provider call. Returns hold_id or None if not saas."""
    if not is_saas():
        return None
    identity = get_billing_identity()
    if identity is None:
        logger.error("saas hold refused: missing billing identity call_id=%s", api_call_id)
        raise ApiError("billing_identity_missing", status_code=503)
    call_id = credit_call_id(api_call_id)
    estimate = _default_hold_estimate()
    try:
        result = await control_plane_internal_hold(
            org_id=identity.org_id,
            user_id=identity.user_id,
            estimate_credits=estimate,
            call_id=call_id,
            task_id=task_id,
            purpose=purpose,
            meta=meta,
        )
    except ControlPlaneError as exc:
        if exc.status_code == 402:
            raise ApiError("insufficient_credits", status_code=402) from exc
        logger.error("saas hold failed call_id=%s status=%s detail=%s", call_id, exc.status_code, exc.detail)
        raise ApiError("control_plane_credits_unavailable", status_code=503) from exc
    return str(result.get("hold_id") or "")


async def settle_api_call_from_db(api_call_id: int, session_factory: Any) -> None:
    """Load cost from ``api_calls`` then settle the matching control-plane hold."""
    if not is_saas():
        return
    from lib.db.models.api_call import ApiCall

    async with session_factory() as session:
        row = await session.get(ApiCall, api_call_id)
        if row is None:
            return
        cost_amount, currency, model = row.cost_amount, row.currency, row.model
    await settle_for_api_call(
        api_call_id=api_call_id,
        cost_amount=cost_amount,
        currency=currency,
        model=model,
    )


async def settle_for_api_call(
    *,
    api_call_id: int,
    cost_amount: float | Decimal | None,
    currency: str | None,
    model: str | None,
    estimate_fallback: bool = True,
) -> None:
    if not is_saas():
        return
    identity = get_billing_identity()
    if identity is None:
        logger.error("saas settle refused: missing billing identity call_id=%s", api_call_id)
        raise ApiError("billing_identity_missing", status_code=503)
    call_id = credit_call_id(api_call_id)
    multiplier = await _cost_to_credits_multiplier()
    actual = cost_to_credits(cost_amount, multiplier=multiplier)
    if estimate_fallback and actual == 0 and cost_amount is None:
        # Unpriced success: consume the provisional hold estimate via settle-at-estimate.
        actual = _default_hold_estimate()
    try:
        kwargs: dict[str, Any] = {
            "org_id": identity.org_id,
            "call_id": call_id,
            "actual_credits": actual,
            "model": model,
        }
        if cost_amount is not None and currency:
            kwargs["provider_cost_amount"] = Decimal(str(cost_amount))
            kwargs["provider_cost_currency"] = currency
        await control_plane_internal_settle(**kwargs)
    except ControlPlaneError as exc:
        if exc.status_code == 404:
            logger.info("saas settle skipped missing hold call_id=%s", call_id)
            return
        logger.error("saas settle failed call_id=%s status=%s detail=%s", call_id, exc.status_code, exc.detail)


async def release_for_api_call(*, api_call_id: int) -> None:
    if not is_saas():
        return
    identity = get_billing_identity()
    if identity is None:
        logger.error("saas release refused: missing billing identity call_id=%s", api_call_id)
        raise ApiError("billing_identity_missing", status_code=503)
    call_id = credit_call_id(api_call_id)
    try:
        await control_plane_internal_release(org_id=identity.org_id, call_id=call_id)
    except ControlPlaneError as exc:
        if exc.status_code == 404:
            return
        logger.error("saas release failed call_id=%s status=%s detail=%s", call_id, exc.status_code, exc.detail)


async def hold_for_agent_turn(
    *,
    session_id: str,
    call_count: int,
    purpose: str = "agent",
) -> str | None:
    if not is_saas() or call_count <= 0:
        return None
    identity = get_billing_identity()
    if identity is None:
        logger.error("saas agent hold refused: missing billing identity session=%s", session_id)
        raise ApiError("billing_identity_missing", status_code=503)
    call_id = f"agent_turn:{session_id}:{int(time.time() * 1000)}"
    estimate = _default_hold_estimate() * Decimal(call_count)
    try:
        result = await control_plane_internal_hold(
            org_id=identity.org_id,
            user_id=identity.user_id,
            estimate_credits=estimate,
            call_id=call_id,
            purpose=purpose,
            meta={"session_id": session_id, "call_count": call_count},
        )
    except ControlPlaneError as exc:
        if exc.status_code == 402:
            raise ApiError("insufficient_credits", status_code=402) from exc
        raise ApiError("control_plane_credits_unavailable", status_code=503) from exc
    return str(result.get("hold_id") or call_id)


async def finalize_agent_turn(
    *,
    hold_ref: str | None,
    total_cost: float | Decimal | None,
    currency: str | None,
    success: bool,
) -> None:
    if not is_saas() or not hold_ref:
        return
    identity = get_billing_identity()
    if identity is None:
        logger.error("saas agent finalize refused: missing billing identity hold=%s", hold_ref)
        raise ApiError("billing_identity_missing", status_code=503)
    if not success:
        try:
            await control_plane_internal_release(org_id=identity.org_id, hold_id=hold_ref)
        except ControlPlaneError as exc:
            if exc.status_code != 404:
                logger.error("saas agent release failed hold=%s detail=%s", hold_ref, exc.detail)
        return
    multiplier = await _cost_to_credits_multiplier()
    actual = cost_to_credits(total_cost, multiplier=multiplier)
    try:
        kwargs: dict[str, Any] = {
            "org_id": identity.org_id,
            "hold_id": hold_ref,
            "actual_credits": actual if actual > 0 else _default_hold_estimate(),
        }
        if total_cost is not None and currency:
            kwargs["provider_cost_amount"] = Decimal(str(total_cost))
            kwargs["provider_cost_currency"] = currency
        await control_plane_internal_settle(**kwargs)
    except ControlPlaneError as exc:
        if exc.status_code != 404:
            logger.error("saas agent settle failed hold=%s detail=%s", hold_ref, exc.detail)
