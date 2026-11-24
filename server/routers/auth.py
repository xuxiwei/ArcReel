"""
认证 API 路由

提供 OAuth2 登录和 token 验证接口。
SaaS 模式下登录/注册代理到控制面，会话 JWT 由控制面签发。
"""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from saas.adapter.control_plane_client import (
    ControlPlaneError,
    control_plane_login,
    control_plane_me,
    control_plane_register,
)
from saas.adapter.mode import get_deployment_mode, is_saas
from server.auth import (
    CurrentUser,
    check_credentials,
    create_token,
    is_auth_enabled,
)
from server.i18n import Translator

logger = logging.getLogger(__name__)

router = APIRouter()

public_router = APIRouter()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class VerifyResponse(BaseModel):
    valid: bool
    username: str
    org_id: str | None = None


class WalletBalanceResponse(BaseModel):
    balance: str
    held: str


class MeWalletResponse(BaseModel):
    org_id: str | None = None
    username: str | None = None
    wallet: WalletBalanceResponse


class AuthStatusResponse(BaseModel):
    enabled: bool
    deployment_mode: Literal["self_hosted", "saas"] = "self_hosted"


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    email: str | None = None


@public_router.get("/auth/status", response_model=AuthStatusResponse)
async def auth_status():
    """暴露 ``AUTH_ENABLED`` 与部署模式供前端 bootstrap。

    前端 ``auth-store.initialize()`` 在 localStorage 无 token 时调用本接口：
    ``enabled=false`` 时跳过登录页直接进主界面；``enabled=true`` 时保留原
    登录链路。``deployment_mode=saas`` 时前端可展示注册入口。
    """
    return AuthStatusResponse(enabled=is_auth_enabled(), deployment_mode=get_deployment_mode())


@public_router.post("/auth/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    _t: Translator,
):
    """用户登录

    自托管：校验本地 ``AUTH_*`` 并签发工作台 JWT。
    SaaS：代理到控制面 ``POST /v1/auth/login``，原样返回控制面 access_token。
    ``AUTH_ENABLED=false`` 时（仅自托管语义）跳过凭据校验直接签发本地 token。
    """
    if is_saas():
        try:
            data = await control_plane_login(
                username=form_data.username,
                password=form_data.password,
            )
        except ControlPlaneError as exc:
            logger.warning("SaaS 登录失败: %s", exc.detail)
            status = exc.status_code if exc.status_code in {401, 403, 409, 503} else 401
            if exc.status_code >= 500:
                status = 503
            raise HTTPException(
                status_code=status,
                detail=exc.detail if status != 401 else _t("unauthorized"),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        logger.info("SaaS 用户登录成功: %s", form_data.username)
        return TokenResponse(access_token=data["access_token"], token_type="bearer")

    if is_auth_enabled() and not check_credentials(form_data.username, form_data.password):
        logger.warning("登录失败: 用户名或密码错误 (用户: %s)", form_data.username)
        raise HTTPException(
            status_code=401,
            detail=_t("unauthorized"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_token(form_data.username)
    logger.info("用户登录成功: %s", form_data.username)
    return TokenResponse(access_token=token, token_type="bearer")


@public_router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register_account(body: RegisterRequest, _t: Translator):
    """SaaS 开放注册（代理控制面）。自托管返回 404。"""
    if not is_saas():
        raise HTTPException(status_code=404, detail="register is only available in saas mode")

    try:
        data = await control_plane_register(
            username=body.username,
            password=body.password,
            email=body.email,
        )
    except ControlPlaneError as exc:
        logger.warning("SaaS 注册失败: %s", exc.detail)
        status = exc.status_code if 400 <= exc.status_code < 500 else 503
        raise HTTPException(status_code=status, detail=exc.detail) from exc

    logger.info("SaaS 用户注册成功: %s", body.username)
    return TokenResponse(access_token=data["access_token"], token_type="bearer")


@router.get("/auth/verify", response_model=VerifyResponse)
async def verify(
    current_user: CurrentUser,
):
    """验证 token 有效性

    使用 OAuth2 Bearer token 依赖自动提取和验证 token。
    """
    return VerifyResponse(
        valid=True,
        username=current_user.sub,
        org_id=current_user.org_id,
    )


def _bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization") or ""
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="未认证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


@router.get("/me/wallet", response_model=MeWalletResponse)
async def me_wallet(request: Request, current_user: CurrentUser):
    """SaaS：代理控制面 ``GET /v1/me`` 返回积分余额；自托管 404。"""
    if not is_saas():
        raise HTTPException(status_code=404, detail="wallet is only available in saas mode")
    try:
        data = await control_plane_me(access_token=_bearer_token(request))
    except ControlPlaneError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 503
        raise HTTPException(status_code=status, detail=exc.detail) from exc
    wallet = data.get("wallet") if isinstance(data, dict) else None
    if not isinstance(wallet, dict):
        raise HTTPException(status_code=502, detail="control plane me missing wallet")
    org = data.get("org") if isinstance(data.get("org"), dict) else {}
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    return MeWalletResponse(
        org_id=str(org.get("id") or current_user.org_id or ""),
        username=str(user.get("username") or current_user.sub or ""),
        wallet=WalletBalanceResponse(
            balance=str(wallet.get("balance", "0")),
            held=str(wallet.get("held", "0")),
        ),
    )
