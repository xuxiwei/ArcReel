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
        {
            "sub": "u1",
            "user_id": "u1",
            "org_id": "o1",
            "aud": "arcreel-control-plane",
            "iss": "arcreel-auth",
            "typ": "access",
            "iat": now,
            "exp": now + 3600,
        },
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


# --------------------------------------------------------------------------- Ed25519 + Agent tokens


def _cp_claims(**extra):
    now = int(time.time())
    return {
        "sub": "u1", "user_id": "u1", "org_id": "o1", "aud": "arcreel-control-plane", "iss": "arcreel-auth",
        "typ": "access", "iat": now, "exp": now + 3600, **extra,
    }


@pytest.fixture
def ed_keys(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from saas.adapter import auth_bridge

    private = Ed25519PrivateKey.generate()
    pub_path = tmp_path / "jwt_ed25519.pub.pem"
    pub_path.write_bytes(
        private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    auth_bridge._read_public_key.cache_clear()
    monkeypatch.setenv("CONTROL_PLANE_JWT_PUBLIC_KEY_PATH", str(pub_path))
    monkeypatch.setenv("CONTROL_PLANE_JWT_SECRET", "s" * 40)  # present but must be ignored
    yield private
    auth_bridge._read_public_key.cache_clear()


@pytest.mark.unit
def test_eddsa_token_verified_with_public_key_only(ed_keys) -> None:
    token = jwt.encode(_cp_claims(), ed_keys, algorithm="EdDSA")
    payload = verify_control_plane_token(token)
    assert payload is not None and payload["user_id"] == "u1" and payload["org_id"] == "o1"


@pytest.mark.unit
def test_hs256_token_rejected_once_public_key_is_configured(ed_keys) -> None:
    forged = jwt.encode(_cp_claims(), "s" * 40, algorithm="HS256")
    assert verify_control_plane_token(forged) is None


@pytest.mark.unit
def test_cp_token_carrying_agent_claim_is_rejected(ed_keys) -> None:
    token = jwt.encode(_cp_claims(embedded_agent=True), ed_keys, algorithm="EdDSA")
    assert verify_control_plane_token(token) is None


@pytest.mark.unit
def test_public_key_path_must_not_be_a_private_key(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from saas.adapter import auth_bridge

    path = tmp_path / "oops.pem"
    path.write_bytes(
        Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    auth_bridge._read_public_key.cache_clear()
    monkeypatch.setenv("CONTROL_PLANE_JWT_PUBLIC_KEY_PATH", str(path))
    with pytest.raises(AuthBridgeError):
        verify_control_plane_token(jwt.encode(_cp_claims(), "k" * 40, algorithm="HS256"))
    auth_bridge._read_public_key.cache_clear()


@pytest.mark.unit
def test_embedded_agent_token_roundtrip_with_workbench_key(ed_keys, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from saas.adapter.auth_bridge import mint_embedded_agent_token

    monkeypatch.setenv("AUTH_TOKEN_SECRET", "w" * 48)
    token = mint_embedded_agent_token(SimpleNamespace(user_id="u7", org_id="o7"), expiry_seconds=60)
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "HS256"
    payload = verify_control_plane_token(token)
    assert payload is not None and payload["embedded_agent"] is True
    assert payload["user_id"] == "u7" and payload["org_id"] == "o7"
    # Not signed with anything the control plane holds: neither its key pair nor a CP secret.
    assert jwt.decode(token, options={"verify_signature": False})["iss"] == "arcreel-workbench"


@pytest.mark.unit
def test_embedded_agent_token_from_another_key_is_rejected(ed_keys, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from saas.adapter.auth_bridge import mint_embedded_agent_token

    monkeypatch.setenv("AUTH_TOKEN_SECRET", "a" * 48)
    token = mint_embedded_agent_token(SimpleNamespace(user_id="u7", org_id="o7"), expiry_seconds=60)
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "b" * 48)
    assert verify_control_plane_token(token) is None
