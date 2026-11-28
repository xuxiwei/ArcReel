"""SaaS: the rates that turn a provider cost into credits, for showing usage in credits.

The same chain the credits hook charges with: cost (currency C) × fx_C→CNY × cny_yuan_to_credits ×
cost_to_credits_multiplier. Any signed-in user may read them (the workbench shows a project's usage
in credits instead of money). 404 when self-hosted; 503 when the control plane has no usable rate.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from saas.adapter.mode import is_saas

router = APIRouter(prefix="/saas", tags=["SaaS 积分"])

# Currencies besides CNY that provider costs are recorded in.
_FX_CURRENCIES = ("USD",)


@router.get("/credit-rates")
async def credit_rates() -> dict[str, Any]:
    if not is_saas():
        raise HTTPException(status_code=404, detail="only available in saas mode")
    from saas.adapter.credits_hook import CreditConversionError, _config_decimal

    try:
        rate = await _config_decimal("cny_yuan_to_credits", "SAAS_CNY_YUAN_TO_CREDITS")
        multiplier = await _config_decimal("cost_to_credits_multiplier", "SAAS_COST_TO_CREDITS_MULTIPLIER")
    except CreditConversionError as exc:
        raise HTTPException(status_code=503, detail="credit_rates_unavailable") from exc
    cny_per: dict[str, str] = {"CNY": "1"}
    for code in _FX_CURRENCIES:
        try:
            cny_per[code] = str(await _config_decimal(f"fx_{code.lower()}_to_cny", f"SAAS_FX_{code}_TO_CNY"))
        except CreditConversionError:
            continue  # that currency's costs are left out of the credit total
    return {"credits_per_cny": str(rate * multiplier), "cny_per": cny_per}
