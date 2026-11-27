"""SaaS secrets leave os.environ after start-up; readers keep working through secret_env."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from saas.adapter import secret_env


@pytest.fixture(autouse=True)
def _clean_vault():
    secret_env.reset_for_tests()
    yield
    secret_env.reset_for_tests()


def test_seal_moves_secret_names_and_keeps_others() -> None:
    env = {
        "CONTROL_PLANE_INTERNAL_TOKEN": "t" * 24,
        "CONTROL_PLANE_URL": "http://127.0.0.1:8100",
        "DATABASE_URL": "postgresql+asyncpg://u:p@127.0.0.1:2368/arcreel",
        "AUTH_PASSWORD": "pw",
        "ARCREEL_API_BASE": "http://127.0.0.1:1241/api/v1",
        "DEPLOYMENT_MODE": "saas",
        "PATH": "/usr/bin",
    }
    sealed = secret_env.seal_secret_env(env)
    assert set(sealed) == {"CONTROL_PLANE_INTERNAL_TOKEN", "CONTROL_PLANE_URL", "DATABASE_URL", "AUTH_PASSWORD"}
    assert set(env) == {"ARCREEL_API_BASE", "DEPLOYMENT_MODE", "PATH"}
    assert secret_env.is_sealed("DATABASE_URL")


def test_sealed_values_are_readable_but_not_inherited(monkeypatch: pytest.MonkeyPatch) -> None:
    from lib.db.engine import get_database_url
    from saas.adapter.control_plane_client import get_internal_token

    url = "postgresql+asyncpg://u:p@127.0.0.1:2368/arcreel_test"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("CONTROL_PLANE_INTERNAL_TOKEN", "i" * 24)
    secret_env.seal_secret_env()

    assert "DATABASE_URL" not in os.environ and "CONTROL_PLANE_INTERNAL_TOKEN" not in os.environ
    assert get_database_url() == url
    assert get_internal_token() == "i" * 24
    child = subprocess.run(
        [sys.executable, "-c", "import os; print(os.environ.get('DATABASE_URL', '-'), os.environ.get('CONTROL_PLANE_INTERNAL_TOKEN', '-'))"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert child.stdout.split() == ["-", "-"]


def test_token_secret_survives_sealing(monkeypatch: pytest.MonkeyPatch) -> None:
    import server.auth as workbench_auth

    workbench_auth.reset_token_secret_for_tests()
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "z" * 48)
    before = workbench_auth.get_token_secret()
    secret_env.seal_secret_env()
    try:
        assert "AUTH_TOKEN_SECRET" not in os.environ
        assert workbench_auth.get_token_secret() == before == "z" * 48
    finally:
        workbench_auth.reset_token_secret_for_tests()


def test_password_check_keeps_the_real_password_after_sealing(monkeypatch: pytest.MonkeyPatch) -> None:
    import server.auth as workbench_auth

    monkeypatch.setattr(workbench_auth, "_cached_password_hash", None)
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_USERNAME", "admin")
    monkeypatch.setenv("AUTH_PASSWORD", "Real-Passw0rd")
    secret_env.seal_secret_env()
    assert "AUTH_PASSWORD" not in os.environ
    assert workbench_auth.check_credentials("admin", "") is False
    assert workbench_auth.check_credentials("admin", "Real-Passw0rd") is True
