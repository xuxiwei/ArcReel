"""
登录 API 路由测试

测试 server.routers.auth 中的登录和 token 验证路由。
"""

import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import server.auth as auth_module
from server.routers import auth as auth_router
from tests.auth_deps import AUTH_DEPENDENCIES


@pytest.fixture
def auth_router_client():
    """创建测试客户端，设置固定的认证环境变量"""
    auth_module._cached_token_secret = None
    auth_module._cached_password_hash = None
    with patch.dict(
        os.environ,
        {
            "AUTH_USERNAME": "testuser",
            "AUTH_PASSWORD": "testpass",
            "AUTH_TOKEN_SECRET": "test-router-secret-key-at-least-32-bytes-long",
        },
    ):
        app = FastAPI()
        app.include_router(auth_router.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
        app.include_router(auth_router.public_router, prefix="/api/v1")
        with TestClient(app) as c:
            yield c


class TestLoginRoute:
    def test_login_success(self, auth_router_client):
        """正确凭据返回 200 + access_token"""
        resp = auth_router_client.post(
            "/api/v1/auth/token",
            data={"username": "testuser", "password": "testpass"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 0

    def test_login_wrong_password(self, auth_router_client):
        """错误密码返回 401"""
        resp = auth_router_client.post(
            "/api/v1/auth/token",
            data={"username": "testuser", "password": "wrongpass"},
        )
        assert resp.status_code == 401

    def test_login_wrong_username(self, auth_router_client):
        """错误用户名返回 401"""
        resp = auth_router_client.post(
            "/api/v1/auth/token",
            data={"username": "wronguser", "password": "testpass"},
        )
        assert resp.status_code == 401


class TestVerifyRoute:
    def test_verify_valid_token(self, auth_router_client):
        """有效 token 验证通过"""
        login_resp = auth_router_client.post(
            "/api/v1/auth/token",
            data={"username": "testuser", "password": "testpass"},
        )
        token = login_resp.json()["access_token"]

        resp = auth_router_client.get(
            "/api/v1/auth/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["username"] == "testuser"

    def test_verify_no_token(self, auth_router_client):
        """缺少 token 返回 401"""
        resp = auth_router_client.get("/api/v1/auth/verify")
        assert resp.status_code == 401

    def test_verify_invalid_token(self, auth_router_client):
        """无效 token 返回 401"""
        resp = auth_router_client.get(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401


class TestSaasLoginRateLimitMapping:
    def test_saas_login_maps_cp_429_with_retry_after(self, monkeypatch):
        """WB-06: CP rate limit must surface as 429 + Retry-After, not fake 401."""
        from saas.adapter.control_plane_client import ControlPlaneError

        monkeypatch.setenv("DEPLOYMENT_MODE", "saas")

        async def _boom(*, username: str, password: str, client_ip: str | None = None):
            raise ControlPlaneError(429, "rate limit exceeded", retry_after="60")

        app = FastAPI()
        app.include_router(auth_router.public_router, prefix="/api/v1")
        with (
            patch("server.routers.auth.is_saas", return_value=True),
            patch("server.routers.auth.control_plane_login", side_effect=_boom),
            TestClient(app) as client,
        ):
            resp = client.post(
                "/api/v1/auth/token",
                data={"username": "anyone", "password": "whatever"},
            )
        assert resp.status_code == 429
        assert resp.json()["detail"] == "rate limit exceeded"
        assert resp.headers.get("retry-after") == "60"


class TestMeWalletControlPlaneAuth:
    def test_cp_401_maps_to_503_not_workbench_logout(self):
        """Control-plane 401 after CurrentUser must not look like session expiry."""
        from saas.adapter.control_plane_client import ControlPlaneError
        from server.auth import CurrentUserInfo, get_current_user

        async def _boom(*, access_token: str):
            raise ControlPlaneError(401, "invalid token")

        app = FastAPI()
        app.include_router(auth_router.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
        app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(
            id="u1", sub="u1", role="member", org_id="o1"
        )
        with (
            patch("server.routers.auth.is_saas", return_value=True),
            patch("server.routers.auth.control_plane_me", side_effect=_boom),
            TestClient(app) as client,
        ):
            resp = client.get(
                "/api/v1/me/wallet",
                headers={"Authorization": "Bearer fake-token"},
            )
        assert resp.status_code == 503
        assert resp.json()["detail"] == "control_plane_unauthorized"
