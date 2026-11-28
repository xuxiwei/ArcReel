"""SaaS: usage is shown in credits with the same rates the credits hook charges with."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from saas.adapter import credits_hook, routes_credit_rates


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes_credit_rates.router, prefix="/api/v1")
    return TestClient(app)


def test_rates_combine_yuan_rate_and_multiplier(monkeypatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("SAAS_CNY_YUAN_TO_CREDITS", "100")
    monkeypatch.setenv("SAAS_COST_TO_CREDITS_MULTIPLIER", "1.5")
    monkeypatch.setenv("SAAS_FX_USD_TO_CNY", "7.2")
    credits_hook.clear_credit_config_cache()
    res = _client().get("/api/v1/saas/credit-rates")
    assert res.status_code == 200, res.text
    body = res.json()
    assert float(body["credits_per_cny"]) == 150
    assert body["cny_per"] == {"CNY": "1", "USD": "7.2"}


def test_self_hosted_is_404(monkeypatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    assert _client().get("/api/v1/saas/credit-rates").status_code == 404
