"""SaaS: providers configured by an active platform key count as ready."""

from __future__ import annotations

import asyncio

import pytest

from saas.adapter import platform_keys
from saas.adapter.control_plane_client import ControlPlaneError


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    platform_keys.clear_platform_key_cache()
    monkeypatch.setattr(platform_keys, "is_saas", lambda: True)
    yield
    platform_keys.clear_platform_key_cache()


def _serve(monkeypatch, rows):
    async def fake():
        if isinstance(rows, Exception):
            raise rows
        return rows

    monkeypatch.setattr(platform_keys, "control_plane_platform_keys", fake)


def test_one_key_makes_the_provider_ready_whatever_its_capability(monkeypatch):
    _serve(monkeypatch, [{"capability": "image", "provider_name": "ark", "secret": "k", "extra": None}])
    assert "ark" in asyncio.run(platform_keys.platform_ready_providers())


def test_a_row_without_the_required_key_is_not_ready(monkeypatch):
    _serve(monkeypatch, [{"capability": "video", "provider_name": "ark", "secret": "", "extra": {"base_url": "x"}}])
    assert asyncio.run(platform_keys.platform_ready_providers()) == frozenset()


def test_unknown_provider_names_are_ignored(monkeypatch):
    _serve(monkeypatch, [{"capability": "video", "provider_name": "not-a-provider", "secret": "k", "extra": None}])
    assert asyncio.run(platform_keys.platform_ready_providers()) == frozenset()


def test_control_plane_down_lists_nothing_instead_of_failing(monkeypatch):
    _serve(monkeypatch, ControlPlaneError(503, "down"))
    assert asyncio.run(platform_keys.platform_ready_providers()) == frozenset()


def test_self_hosted_is_unaffected(monkeypatch):
    monkeypatch.setattr(platform_keys, "is_saas", lambda: False)
    _serve(monkeypatch, [{"capability": "image", "provider_name": "ark", "secret": "k", "extra": None}])
    assert asyncio.run(platform_keys.platform_ready_providers()) == frozenset()
