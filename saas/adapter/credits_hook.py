"""SaaS credit hold / settle / release beside the workbench cost ledger.

Pricing chain (all values come from the control plane, cached, env can override):

    provider cost (currency C) × fx_<c>_to_cny × cny_yuan_to_credits × cost_to_credits_multiplier

All money in the SaaS layer is CNY: a missing currency means CNY, and the cost
sent to the control-plane ledger is the CNY amount (``api_calls`` keeps the
provider's original currency for reconciliation). ``CNY`` needs no fx rate. A cost that cannot be converted (unknown currency, control
plane unreachable with no cached value) is never settled below the hold: the call is
charged its hold estimate and an error is logged.
"""

from __future__ import annotations

import logging
import math
import os
import time
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from lib.infra.api_errors import ApiError

from saas.adapter.billing_context import BillingIdentity, get_billing_identity
from saas.adapter.control_plane_client import (
    ControlPlaneError,
    control_plane_internal_config,
    control_plane_internal_hold,
    control_plane_internal_release,
    control_plane_internal_release_by_calls,
    control_plane_internal_release_stale,
    control_plane_internal_settle,
)
from saas.adapter.mode import is_saas

logger = logging.getLogger(__name__)

_QUANT = Decimal("0.000001")
_COST_QUANT = Decimal("0.00000001")
_DEFAULT_HOLD = Decimal("10")
_CONFIG_TTL_SEC = 60.0
_VIDEO_ESTIMATE_SECONDS = 5
AGENT_TURN_PREFIX = "agent_turn:"

# key -> (fetched_at, value); the last good value survives control-plane outages.
_config_cache: dict[str, tuple[float, Decimal]] = {}


class CreditConversionError(Exception):
    """A provider cost could not be turned into credits."""


def clear_credit_config_cache() -> None:
    _config_cache.clear()


def _positive_decimal(raw: str) -> Decimal | None:
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() and value > 0 else None


async def _config_decimal(key: str, env_name: str) -> Decimal:
    env = os.environ.get(env_name, "").strip()
    if env:
        value = _positive_decimal(env)
        if value is None:
            raise CreditConversionError(f"{env_name} must be a finite number > 0")
        return value
    now = time.monotonic()
    cached = _config_cache.get(key)
    if cached is not None and now - cached[0] < _CONFIG_TTL_SEC:
        return cached[1]
    try:
        value = _positive_decimal(await control_plane_internal_config(key))
    except ControlPlaneError as exc:
        if cached is not None:
            logger.warning("control-plane config %s unavailable (%s); using last value", key, exc.detail)
            return cached[1]
        raise CreditConversionError(f"control-plane config {key} unavailable: {exc.detail}") from exc
    if value is None:
        raise CreditConversionError(f"control-plane config {key} is not a positive number")
    _config_cache[key] = (now, value)
    return value


async def cost_to_cny(cost_amount: float | Decimal, currency: str | None) -> Decimal:
    """Provider cost → CNY (missing currency = CNY). Raises instead of guessing a rate."""
    amount = Decimal(str(cost_amount))
    if not amount.is_finite():
        raise CreditConversionError(f"non-finite cost {cost_amount!r}")
    if amount <= 0:
        return Decimal("0")
    code = (currency or "CNY").strip().upper()
    if code == "CNY":
        return amount
    if not (len(code) == 3 and code.isalpha()):
        raise CreditConversionError(f"unsupported currency {currency!r}")
    fx = await _config_decimal(f"fx_{code.lower()}_to_cny", f"SAAS_FX_{code}_TO_CNY")
    return amount * fx


async def cost_to_credits(cost_amount: float | Decimal, currency: str | None) -> Decimal:
    """Provider cost → credits. Raises :class:`CreditConversionError` instead of guessing."""
    cny = await cost_to_cny(cost_amount, currency)
    if cny <= 0:
        return Decimal("0")
    rate = await _config_decimal("cny_yuan_to_credits", "SAAS_CNY_YUAN_TO_CREDITS")
    multiplier = await _config_decimal("cost_to_credits_multiplier", "SAAS_COST_TO_CREDITS_MULTIPLIER")
    return (cny * rate * multiplier).quantize(_QUANT, rounding=ROUND_HALF_UP)


def hold_estimate(call_type: str | None = None, duration_seconds: int | None = None) -> Decimal:
    """Provisional hold: ``SAAS_HOLD_ESTIMATE_<CALL_TYPE>`` → ``SAAS_HOLD_ESTIMATE_CREDITS`` → 10.

    Video scales with duration in 5-second blocks so a long clip cannot run on a
    one-clip hold. The hold only gates the call; settle charges the actual cost.
    """
    raw = ""
    if call_type:
        raw = os.environ.get(f"SAAS_HOLD_ESTIMATE_{call_type.strip().upper()}", "").strip()
    raw = raw or os.environ.get("SAAS_HOLD_ESTIMATE_CREDITS", "").strip()
    base = _positive_decimal(raw) if raw else None
    base = base or _DEFAULT_HOLD
    if call_type in ("video", "reference_video") and duration_seconds and duration_seconds > 0:
        base = base * math.ceil(duration_seconds / _VIDEO_ESTIMATE_SECONDS)
    return base.quantize(_QUANT, rounding=ROUND_HALF_UP)


def _started_stamp(started_at: datetime | None) -> str:
    if started_at is None:
        return "0"
    if started_at.tzinfo is not None:
        started_at = started_at.astimezone(UTC).replace(tzinfo=None)
    return started_at.strftime("%Y%m%d%H%M%S%f")


def credit_call_id(api_call_id: int, started_at: datetime | None) -> str:
    """Idempotency key for one ``api_calls`` row.

    The local id alone is not unique over time: SQLite reuses ids after a reset or
    after deleting the newest rows, and the control plane refuses to hold a
    finalized ``call_id`` again. The row's start time makes the key unique.
    """
    return f"api_call:{api_call_id}:{_started_stamp(started_at)}"


def _legacy_call_ids(api_call_id: int, identity: BillingIdentity | None) -> list[str]:
    """Keys used before ``credit_call_id`` included the start time (in-flight holds at upgrade)."""
    ids = [f"api_call:{api_call_id}"]
    if identity is not None:
        ids.insert(0, f"org:{identity.org_id}:api_call:{api_call_id}")
    return ids


def _require_identity(what: str, ref: object) -> BillingIdentity:
    identity = get_billing_identity()
    if identity is None:
        logger.error("saas %s refused: missing billing identity ref=%s", what, ref)
        raise ApiError("billing_identity_missing", status_code=503)
    return identity


async def _load_calls(session_factory: Any, call_ids: list[int]) -> list[Any]:
    from sqlalchemy import select

    from lib.db.models.api_call import ApiCall

    if not call_ids:
        return []
    async with session_factory() as session:
        return list((await session.execute(select(ApiCall).where(ApiCall.id.in_(call_ids)))).scalars().all())


async def _load_call(session_factory: Any, api_call_id: int) -> Any | None:
    rows = await _load_calls(session_factory, [api_call_id])
    return rows[0] if rows else None


async def _provider_cost_kwargs(cost_amount: float | Decimal | None, currency: str | None) -> dict[str, Any]:
    """Provider cost for the control-plane ledger, always in CNY; {} when it cannot be converted."""
    if cost_amount is None:
        return {}
    try:
        cny = await cost_to_cny(cost_amount, currency)
    except CreditConversionError:
        return {}
    return {
        "provider_cost_amount": cny.quantize(_COST_QUANT, rounding=ROUND_HALF_UP),
        "provider_cost_currency": "CNY",
    }


async def _actual_credits_for(row: Any) -> Decimal:
    estimate = hold_estimate(row.call_type, row.duration_seconds)
    if row.cost_amount is None:
        # Unpriced success: consume the provisional hold estimate.
        return estimate
    try:
        return await cost_to_credits(row.cost_amount, row.currency)
    except CreditConversionError as exc:
        logger.error("saas cost conversion failed api_call=%s: %s; charging hold estimate", row.id, exc)
        return estimate


# --------------------------------------------------------------------------- api_calls


async def hold_for_api_call(
    *,
    api_call_id: int,
    session_factory: Any,
    task_id: str | None,
    purpose: str | None,
    call_type: str | None = None,
    duration_seconds: int | None = None,
    meta: dict[str, Any] | None = None,
) -> str | None:
    """Hold credits before a billable provider call. Returns hold_id, or None when not SaaS."""
    if not is_saas():
        return None
    identity = _require_identity("hold", api_call_id)
    row = await _load_call(session_factory, api_call_id)
    call_id = credit_call_id(api_call_id, row.started_at if row is not None else None)
    try:
        result = await control_plane_internal_hold(
            org_id=identity.org_id,
            user_id=identity.user_id,
            estimate_credits=hold_estimate(call_type, duration_seconds),
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
    identity = _require_identity("settle", api_call_id)
    row = await _load_call(session_factory, api_call_id)
    if row is None:
        return
    actual = await _actual_credits_for(row)
    base: dict[str, Any] = {"org_id": identity.org_id, "actual_credits": actual, "model": row.model}
    base.update(await _provider_cost_kwargs(row.cost_amount, row.currency))
    for call_id in [credit_call_id(api_call_id, row.started_at), *_legacy_call_ids(api_call_id, identity)]:
        try:
            await control_plane_internal_settle(call_id=call_id, **base)
            return
        except ControlPlaneError as exc:
            if exc.status_code == 404:
                continue
            logger.error("saas settle failed call_id=%s status=%s detail=%s", call_id, exc.status_code, exc.detail)
            return
    logger.info("saas settle skipped: no active hold for api_call=%s", api_call_id)


async def release_for_api_call(*, api_call_id: int, session_factory: Any) -> None:
    if not is_saas():
        return
    identity = _require_identity("release", api_call_id)
    row = await _load_call(session_factory, api_call_id)
    started_at = row.started_at if row is not None else None
    for call_id in [credit_call_id(api_call_id, started_at), *_legacy_call_ids(api_call_id, identity)]:
        try:
            await control_plane_internal_release(org_id=identity.org_id, call_id=call_id)
            return
        except ControlPlaneError as exc:
            if exc.status_code == 404:
                continue
            logger.error("saas release failed call_id=%s status=%s detail=%s", call_id, exc.status_code, exc.detail)
            return


async def release_interrupted_calls(call_ids: list[int], session_factory: Any) -> None:
    """Start-up sweep: calls closed at zero cost after a crash must not keep their holds frozen.

    Runs without a billing identity (no request); the control plane releases by
    ``call_id`` across orgs on the internal channel.
    """
    if not is_saas() or not call_ids:
        return
    rows = await _load_calls(session_factory, call_ids)
    keys = [credit_call_id(row.id, row.started_at) for row in rows]
    keys += [f"api_call:{row.id}" for row in rows]  # legacy un-prefixed keys
    try:
        for start in range(0, len(keys), 500):
            await control_plane_internal_release_by_calls(keys[start : start + 500])
    except ControlPlaneError as exc:
        logger.error("saas release of interrupted calls failed: %s", exc.detail)


# --------------------------------------------------------------------------- agent turns


async def hold_for_agent_turn(*, session_id: str, identity: BillingIdentity | None) -> str:
    """Hold credits before an Agent turn starts; 402 stops the message from reaching the CLI."""
    if identity is None:
        logger.error("saas agent hold refused: missing billing identity session=%s", session_id)
        raise ApiError("billing_identity_missing", status_code=503)
    call_id = f"{AGENT_TURN_PREFIX}{session_id}:{time.time_ns()}"
    try:
        result = await control_plane_internal_hold(
            org_id=identity.org_id,
            user_id=identity.user_id,
            estimate_credits=hold_estimate("agent"),
            call_id=call_id,
            purpose="agent",
            meta={"session_id": session_id},
        )
    except ControlPlaneError as exc:
        if exc.status_code == 402:
            raise ApiError("insufficient_credits", status_code=402) from exc
        logger.error("saas agent hold failed session=%s detail=%s", session_id, exc.detail)
        raise ApiError("control_plane_credits_unavailable", status_code=503) from exc
    hold_id = result.get("hold_id")
    if not hold_id:
        raise ApiError("control_plane_credits_unavailable", status_code=503)
    return str(hold_id)


async def release_agent_turn(*, hold_ref: str | None, identity: BillingIdentity | None) -> None:
    if not is_saas() or not hold_ref or identity is None:
        return
    try:
        await control_plane_internal_release(org_id=identity.org_id, hold_id=hold_ref)
    except ControlPlaneError as exc:
        if exc.status_code != 404:
            logger.error("saas agent release failed hold=%s detail=%s", hold_ref, exc.detail)


async def settle_agent_turn(
    *,
    hold_ref: str | None,
    call_ids: list[int],
    session_factory: Any,
    identity: BillingIdentity | None,
    session_id: str,
) -> None:
    """Charge an Agent turn at the cost of the ``api_calls`` rows it wrote.

    Interrupted and failed turns are charged too: their completed requests were
    paid for. Without a hold (e.g. a queued message that started a new turn) a
    zero hold is opened first, so settle still collects what the balance allows.
    """
    if not is_saas():
        return
    if identity is None:
        logger.error("saas agent settle refused: missing billing identity session=%s", session_id)
        return
    rows = await _load_calls(session_factory, call_ids)
    total = Decimal("0")
    cost_cny: Decimal | None = Decimal("0")
    for row in rows:
        if row.cost_amount is None:
            total += hold_estimate("agent")
            cost_cny = None
            continue
        try:
            total += await cost_to_credits(row.cost_amount, row.currency)
            if cost_cny is not None:
                cost_cny += await cost_to_cny(row.cost_amount, row.currency)
        except CreditConversionError as exc:
            logger.error("saas agent cost conversion failed api_call=%s: %s; charging estimate", row.id, exc)
            total += hold_estimate("agent")
            cost_cny = None

    if total <= 0:
        await release_agent_turn(hold_ref=hold_ref, identity=identity)
        return
    try:
        if not hold_ref:
            opened = await control_plane_internal_hold(
                org_id=identity.org_id,
                user_id=identity.user_id,
                estimate_credits=Decimal("0"),
                call_id=f"{AGENT_TURN_PREFIX}{session_id}:{time.time_ns()}",
                purpose="agent",
                meta={"session_id": session_id, "post_paid": True},
            )
            hold_ref = str(opened.get("hold_id") or "")
        kwargs: dict[str, Any] = {"org_id": identity.org_id, "hold_id": hold_ref, "actual_credits": total}
        if cost_cny is not None:
            kwargs.update(await _provider_cost_kwargs(cost_cny, "CNY"))
        await control_plane_internal_settle(**kwargs)
    except ControlPlaneError as exc:
        logger.error("saas agent settle failed session=%s hold=%s detail=%s", session_id, hold_ref, exc.detail)


async def release_stale_agent_holds(*, older_than_seconds: int = 6 * 3600) -> None:
    """Start-up: Agent turns cut off by a crash never reach settle; free their holds."""
    if not is_saas():
        return
    try:
        await control_plane_internal_release_stale(
            call_id_prefix=AGENT_TURN_PREFIX, older_than_seconds=older_than_seconds
        )
    except ControlPlaneError as exc:
        logger.error("saas stale agent hold release failed: %s", exc.detail)
