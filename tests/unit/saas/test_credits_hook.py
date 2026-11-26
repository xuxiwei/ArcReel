"""Unit tests for SaaS credit conversion helpers."""

from __future__ import annotations

from decimal import Decimal

from saas.adapter.billing_context import BillingIdentity, bind_billing_identity
from saas.adapter.credits_hook import cost_to_credits, credit_call_id


def test_credit_call_id_without_identity() -> None:
    assert credit_call_id(42) == "api_call:42"


def test_credit_call_id_includes_org() -> None:
    with bind_billing_identity(BillingIdentity(user_id="u1", org_id="org-9")):
        assert credit_call_id(42) == "org:org-9:api_call:42"


def test_cost_to_credits_multiplier() -> None:
    assert cost_to_credits(1.5, multiplier=Decimal("10")) == Decimal("15.000000")
    assert cost_to_credits(None, multiplier=Decimal("10")) == Decimal("0")
    assert cost_to_credits(-1, multiplier=Decimal("10")) == Decimal("0")
