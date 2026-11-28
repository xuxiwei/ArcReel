"""SaaS: platform Ark keys can use the asset library; the switch and failed links fall back to images."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from lib.asset_library import generation_inputs
from lib.asset_library.bindings import AssetLibraryScope
from lib.backends.provider_assets import REFERENCE_IMAGE_ROLE, InferenceCredentialRef
from saas.adapter import asset_library_platform as alp

OVERLAYS = {
    "ark": {"api_key": "payg-key"},
    "ark-agent-plan": {"api_key": "plan-key", "base_url": "https://ark.cn-beijing.volces.com/api/plan/v3/"},
    "kling": {"api_key": "k"},
}


@pytest.fixture
def saas(monkeypatch):
    monkeypatch.setattr(alp, "is_saas", lambda: True)

    async def overlays():
        return OVERLAYS

    monkeypatch.setattr(alp, "_overlays", overlays)


def test_platform_ark_keys_are_bindable(saas):
    creds = asyncio.run(alp.platform_bindable_credentials())
    assert [(c.credential_type, c.credential_id, c.provider) for c in creds] == [
        ("platform", 1, "ark"),
        ("platform", 2, "ark-agent-plan"),
    ]
    assert creds[0].endpoint.startswith("https://")
    assert creds[1].endpoint == "https://ark.cn-beijing.volces.com/api/plan/v3"


def test_nothing_is_bindable_when_self_hosted(monkeypatch):
    monkeypatch.setattr(alp, "is_saas", lambda: False)
    assert asyncio.run(alp.platform_bindable_credentials()) == []
    assert asyncio.run(alp.platform_credential_id("ark", {"api_key": "payg-key"})) is None


def test_platform_credential_id_only_for_the_platform_key(saas):
    assert asyncio.run(alp.platform_credential_id("ark", {"api_key": "payg-key"})) == 1
    assert asyncio.run(alp.platform_credential_id("ark", {"api_key": "someone-elses"})) is None
    assert asyncio.run(alp.platform_credential_id("kling", {"api_key": "k"})) is None


@pytest.mark.parametrize(("raw", "expected"), [("", True), ("true", True), ("false", False), ("off", False)])
def test_switch_values(raw, expected):
    assert alp.parse_enabled(raw) is expected


def _backend():
    return SimpleNamespace(
        provider_asset_roles=frozenset({REFERENCE_IMAGE_ROLE}),
        inference_credential=InferenceCredentialRef(
            credential_type="platform", credential_id=1, api_key="payg-key", base_url=None
        ),
    )


SCOPE = AssetLibraryScope(account_id=1, account_identity="id", site="volcengine", region="cn-beijing", project_name="d")


@pytest.mark.parametrize(("enabled", "expected"), [(True, SCOPE), (False, None)])
def test_switch_off_means_no_library(monkeypatch, enabled, expected):
    async def is_enabled(_session):
        return enabled

    async def bound(_session, **kwargs):
        assert kwargs["credential_type"] == "platform"
        return SCOPE

    monkeypatch.setattr(alp, "asset_library_enabled", is_enabled)
    monkeypatch.setattr(generation_inputs, "resolve_bound_scope", bound)
    assert asyncio.run(generation_inputs.call_scope(object(), _backend())) == expected


def _choose(monkeypatch, *, saas_mode: bool, state: str):
    monkeypatch.setattr(alp, "is_saas", lambda: saas_mode)
    link = SimpleNamespace(id=7, state=state, selected=True, provider_asset_id=None, error_code="X", error_message=None)

    async def selected(_session, **_kwargs):
        return link

    monkeypatch.setattr(generation_inputs, "selected_link", selected)
    monkeypatch.setattr(generation_inputs, "_content_version_ids", lambda _path, sources: ["v1"] * len(sources))

    @asynccontextmanager
    async def factory():
        yield object()

    sources = [generation_inputs.ReferenceImageSource(locator="characters/a.png", sha256="s", name="A")]
    return asyncio.run(
        generation_inputs.choose_in_scope(factory, scope=SCOPE, project_name="p", project_path=None, sources=sources)
    )


def test_failed_link_sends_the_image_in_saas(monkeypatch):
    assert _choose(monkeypatch, saas_mode=True, state="failed") == (None,)


def test_failed_link_still_blocks_when_self_hosted(monkeypatch):
    with pytest.raises(generation_inputs.ProviderAssetLinkUnavailableError):
        _choose(monkeypatch, saas_mode=False, state="failed")


def test_processing_link_still_waits(monkeypatch):
    with pytest.raises(generation_inputs.ProviderAssetLinkUnavailableError):
        _choose(monkeypatch, saas_mode=True, state="processing")
