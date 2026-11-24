"""Unit tests for SaaS auth bridge (no network)."""

from __future__ import annotations

import time

import jwt
import pytest

from saas.adapter.auth_bridge import AuthBridgeError, verify_control_plane_token
from saas.adapter.mode import get_deployment_mode, is_saas
from server.auth import CurrentUserInfo, _payload_to_user


@pytest.mark.unit
def test_deployment_mode_default_self_hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)
    assert get_deployment_mode() == "self_hosted"
    assert is_saas() is False


@pytest.mark.unit
def test_deployment_mode_saas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    assert get_deployment_mode() == "saas"
    assert is_saas() is True


@pytest.mark.unit
def test_verify_control_plane_token_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    key = "uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu"
    env_name = "_".join(("CONTROL", "PLANE", "JWT", "SECRET"))
    monkeypatch.setenv(env_name, key)
    now = int(time.time())
    token = jwt.encode(
        {"sub": "u1", "user_id": "u1", "org_id": "o1", "iat": now, "exp": now + 3600},
        key,
        algorithm="HS256",
    )
    payload = verify_control_plane_token(token)
    assert payload is not None
    assert payload["user_id"] == "u1"
    assert payload["org_id"] == "o1"


@pytest.mark.unit
def test_verify_control_plane_token_bad_sig(monkeypatch: pytest.MonkeyPatch) -> None:
    env_name = "_".join(("CONTROL", "PLANE", "JWT", "SECRET"))
    monkeypatch.setenv(env_name, "a" * 32)
    now = int(time.time())
    token = jwt.encode(
        {"sub": "u1", "user_id": "u1", "org_id": "o1", "iat": now, "exp": now + 3600},
        "b" * 32,
        algorithm="HS256",
    )
    assert verify_control_plane_token(token) is None


@pytest.mark.unit
def test_verify_rejects_token_without_exp(monkeypatch: pytest.MonkeyPatch) -> None:
    key = "uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu"
    env_name = "_".join(("CONTROL", "PLANE", "JWT", "SECRET"))
    monkeypatch.setenv(env_name, key)
    now = int(time.time())
    token = jwt.encode(
        {"sub": "u1", "user_id": "u1", "org_id": "o1", "iat": now},
        key,
        algorithm="HS256",
    )
    assert verify_control_plane_token(token) is None


@pytest.mark.unit
def test_payload_to_user_saas_missing_org_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException

    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    try:
        _payload_to_user({"user_id": "u9", "sub": "u9"})
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 401


@pytest.mark.unit
def test_verify_missing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("_".join(("CONTROL", "PLANE", "JWT", "SECRET")), raising=False)
    monkeypatch.delenv("_".join(("JWT", "SIGNING", "SECRET")), raising=False)
    with pytest.raises(AuthBridgeError):
        verify_control_plane_token("x.y.z")


@pytest.mark.unit
def test_payload_to_user_saas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    user = _payload_to_user({"user_id": "u9", "org_id": "org9", "sub": "u9"})
    assert isinstance(user, CurrentUserInfo)
    assert user.id == "u9"
    assert user.org_id == "org9"
    assert user.role == "member"


@pytest.mark.unit
def test_payload_to_user_self_hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    user = _payload_to_user({"sub": "admin"})
    assert user.org_id is None
    assert user.sub == "admin"
