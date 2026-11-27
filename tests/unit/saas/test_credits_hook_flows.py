"""SaaS billing flows: legacy call_id fallback, cost conversion on settle, Agent post-paid turns."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
import pytest
from saas.adapter import credits_hook as ch
from saas.adapter.billing_context import BillingIdentity, bind_billing_identity
from saas.adapter.control_plane_client import ControlPlaneError

ID = BillingIdentity(user_id="u1", org_id="org1")
ROW = SimpleNamespace(id=7, started_at=datetime(2026, 11, 26, 1, 2, 3), cost_amount=0.5, currency="USD",
                      model="m", call_type="video", duration_seconds=10)

@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("SAAS_FX_USD_TO_CNY", "7"); monkeypatch.setenv("SAAS_CNY_YUAN_TO_CREDITS", "10")
    monkeypatch.setenv("SAAS_COST_TO_CREDITS_MULTIPLIER", "1")

async def _rows(factory, ids): return [r for r in [ROW] if r.id in ids]

@pytest.mark.asyncio
async def test_settle_falls_back_to_legacy_key(monkeypatch):
    seen = []
    async def settle(**kw):
        seen.append(kw["call_id"])
        if kw["call_id"].endswith("20261126010203000000"): raise ControlPlaneError(404, "nf")
        return {}
    monkeypatch.setattr(ch, "_load_calls", _rows); monkeypatch.setattr(ch, "control_plane_internal_settle", settle)
    with bind_billing_identity(ID):
        await ch.settle_api_call_from_db(7, None)
    assert seen == ["api_call:7:20261126010203000000", "org:org1:api_call:7"]

@pytest.mark.asyncio
async def test_settle_amount_and_hold_estimate(monkeypatch):
    got = {}
    async def settle(**kw): got.update(kw); return {}
    async def hold(**kw): got["estimate"] = kw["estimate_credits"]; return {"hold_id": "h"}
    monkeypatch.setattr(ch, "_load_calls", _rows); monkeypatch.setattr(ch, "control_plane_internal_settle", settle)
    monkeypatch.setattr(ch, "control_plane_internal_hold", hold)
    with bind_billing_identity(ID):
        await ch.hold_for_api_call(api_call_id=7, session_factory=None, task_id=None, purpose="video", call_type="video", duration_seconds=10)
        await ch.settle_api_call_from_db(7, None)
    assert got["estimate"] == Decimal("20.000000")         # 2 × 5-second blocks
    assert got["actual_credits"] == Decimal("35.000000")   # $0.5 × 7 × 10
    # Ledger cost is recorded in CNY ($0.5 × 7), not the provider currency.
    assert got["provider_cost_amount"] == Decimal("3.50000000") and got["provider_cost_currency"] == "CNY"

@pytest.mark.asyncio
async def test_agent_turn_without_hold_is_post_paid(monkeypatch):
    calls = []
    async def hold(**kw): calls.append(("hold", kw["estimate_credits"])); return {"hold_id": "h0"}
    async def settle(**kw): calls.append(("settle", kw["hold_id"], kw["actual_credits"])); return {}
    agent_row = SimpleNamespace(id=9, started_at=None, cost_amount=0.1, currency="USD", model="claude", call_type="text", duration_seconds=None)
    async def rows(f, ids): return [agent_row]
    monkeypatch.setattr(ch, "_load_calls", rows); monkeypatch.setattr(ch, "control_plane_internal_hold", hold)
    monkeypatch.setattr(ch, "control_plane_internal_settle", settle)
    await ch.settle_agent_turn(hold_ref=None, call_ids=[9], session_factory=None, identity=ID, session_id="s1")
    assert calls == [("hold", Decimal("0")), ("settle", "h0", Decimal("7.000000"))]

@pytest.mark.asyncio
async def test_agent_hold_insufficient_is_402(monkeypatch):
    async def hold(**kw): raise ControlPlaneError(402, "insufficient")
    monkeypatch.setattr(ch, "control_plane_internal_hold", hold)
    with pytest.raises(ch.ApiError) as e:
        await ch.hold_for_agent_turn(session_id="s", identity=ID)
    assert e.value.status_code == 402

@pytest.mark.asyncio
async def test_interrupted_release_sends_new_and_legacy_keys(monkeypatch):
    sent = []
    async def rel(keys): sent.extend(keys); return len(keys)
    monkeypatch.setattr(ch, "_load_calls", _rows); monkeypatch.setattr(ch, "control_plane_internal_release_by_calls", rel)
    await ch.release_interrupted_calls([7], None)
    assert sent == ["api_call:7:20261126010203000000", "api_call:7"]

@pytest.mark.asyncio
async def test_settle_retries_transient_control_plane_errors(monkeypatch):
    attempts = []
    async def settle(**kw):
        attempts.append(kw["call_id"])
        if len(attempts) < 3: raise ControlPlaneError(503, "control plane unreachable")
        return {}
    async def no_sleep(_): return None
    monkeypatch.setattr(ch, "_load_calls", _rows); monkeypatch.setattr(ch, "control_plane_internal_settle", settle)
    monkeypatch.setattr(ch.asyncio, "sleep", no_sleep)
    with bind_billing_identity(ID):
        await ch.settle_api_call_from_db(7, None)
    # Same key retried until it succeeded; the hold is not left frozen.
    assert attempts == ["api_call:7:20261126010203000000"] * 3

@pytest.mark.asyncio
async def test_settle_does_not_retry_client_errors(monkeypatch):
    attempts = []
    async def settle(**kw): attempts.append(1); raise ControlPlaneError(409, "hold_not_active")
    monkeypatch.setattr(ch, "_load_calls", _rows); monkeypatch.setattr(ch, "control_plane_internal_settle", settle)
    with bind_billing_identity(ID):
        await ch.settle_api_call_from_db(7, None)
    assert attempts == [1]

@pytest.mark.asyncio
@pytest.mark.parametrize(("cost", "expected"), [(0.2, "settle"), (0, "release"), (None, "release")])
async def test_failed_call_bills_partial_consumption(monkeypatch, cost, expected):
    done = []
    row = SimpleNamespace(**{**ROW.__dict__, "cost_amount": cost})
    async def rows(f, ids): return [row]
    async def settle(**kw): done.append("settle"); return {}
    async def release(**kw): done.append("release"); return {}
    monkeypatch.setattr(ch, "_load_calls", rows); monkeypatch.setattr(ch, "control_plane_internal_settle", settle)
    monkeypatch.setattr(ch, "control_plane_internal_release", release)
    with bind_billing_identity(ID):
        await ch.finalize_failed_api_call(api_call_id=7, session_factory=None)
    assert done == [expected]
