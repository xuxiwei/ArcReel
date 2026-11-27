"""
认证 API 路由

提供 OAuth2 登录和 token 验证接口。
SaaS 模式下登录/注册代理到控制面，会话 JWT 由控制面签发。
"""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
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
    EMBEDDED_AGENT_SUB,
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
    """Credits plus the CNY view the control plane computes (credits ÷ cny_yuan_to_credits)."""

    balance: str
    held: str
    currency: str = "CNY"
    balance_cny: str | None = None
    held_cny: str | None = None
    credits_per_cny: str | None = None


class MeWalletResponse(BaseModel):
    org_id: str | None = None
    username: str | None = None
    # SaaS PATCH: platform admin (control-plane users.is_admin); the frontend hides admin-only pages otherwise.
    is_admin: bool = False
    wallet: WalletBalanceResponse


class AuthStatusResponse(BaseModel):
    enabled: bool
    deployment_mode: Literal["self_hosted", "saas"] = "self_hosted"


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    email: str | None = None
    # SaaS PATCH: forwarded to the control plane, which checks it in invite-only registration mode.
    invite_code: str | None = Field(default=None, max_length=32)


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)


def _client_ip(request: Request) -> str | None:
    """Browser address as uvicorn sees it (honours its trusted proxy-headers setting)."""
    return request.client.host if request.client else None


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
    request: Request,
    response: Response,
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
                client_ip=_client_ip(request),
            )
        except ControlPlaneError as exc:
            logger.warning("SaaS 登录失败: %s", exc.detail)
            status = exc.status_code if exc.status_code in {401, 403, 409, 429, 503} else 401
            if exc.status_code >= 500:
                status = 503
            headers: dict[str, str] = {}
            if status in {401, 403}:
                headers["WWW-Authenticate"] = "Bearer"
            if status == 429 and exc.retry_after:
                headers["Retry-After"] = str(exc.retry_after)
            raise HTTPException(
                status_code=status,
                detail=exc.detail if status != 401 else _t("unauthorized"),
                headers=headers or None,
            ) from exc
        from saas.adapter.auth_bridge import verify_control_plane_token
        from saas.adapter.local_user import ensure_local_saas_user

        claims = verify_control_plane_token(data["access_token"])
        if claims and claims.get("user_id"):
            await ensure_local_saas_user(str(claims["user_id"]), username=form_data.username)
            _issue_media_cookie(request, response, claims)
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
async def register_account(request: Request, response: Response, body: RegisterRequest, _t: Translator):
    """SaaS 开放注册（代理控制面）。自托管返回 404。"""
    if not is_saas():
        raise HTTPException(status_code=404, detail="register is only available in saas mode")

    try:
        data = await control_plane_register(
            username=body.username,
            password=body.password,
            email=body.email,
            invite_code=body.invite_code,
            client_ip=_client_ip(request),
        )
    except ControlPlaneError as exc:
        logger.warning("SaaS 注册失败: %s", exc.detail)
        status = exc.status_code if 400 <= exc.status_code < 500 else 503
        raise HTTPException(status_code=status, detail=exc.detail) from exc

    from saas.adapter.auth_bridge import verify_control_plane_token
    from saas.adapter.local_user import ensure_local_saas_user

    claims = verify_control_plane_token(data["access_token"])
    if claims and claims.get("user_id"):
        await ensure_local_saas_user(str(claims["user_id"]), username=body.username)
        _issue_media_cookie(request, response, claims)
    logger.info("SaaS 用户注册成功: %s", body.username)
    return TokenResponse(access_token=data["access_token"], token_type="bearer")


def _issue_media_cookie(request: Request, response: Response, claims: dict) -> None:
    # SaaS PATCH: media cookie with the login response (saas/isolation/media_access.py).
    from saas.isolation.media_access import issue_media_cookie

    if claims.get("org_id"):
        issue_media_cookie(request, response, org_id=str(claims["org_id"]), user_id=str(claims["user_id"]))


@public_router.post("/auth/logout", status_code=204)
async def logout(response: Response) -> Response:
    """SaaS PATCH: forget the media cookie. Tokens are kept by the browser only, so nothing else to revoke."""
    from saas.isolation.media_access import clear_media_cookie

    result = Response(status_code=204)
    clear_media_cookie(result)
    return result


@router.get("/auth/verify", response_model=VerifyResponse)
async def verify(
    current_user: CurrentUser,
):
    """验证 token 有效性

    使用 OAuth2 Bearer token 依赖自动提取和验证 token。
    """
    username = current_user.sub
    if is_saas():
        # WB-08: ``sub`` is the control-plane user id in SaaS; return the login name.
        from saas.adapter.local_user import local_username

        username = await local_username(current_user.id) or current_user.id
    return VerifyResponse(
        valid=True,
        username=username,
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
        is_admin=bool(user.get("is_admin")) and current_user.sub != EMBEDDED_AGENT_SUB,
        wallet=WalletBalanceResponse(
            balance=str(wallet.get("balance", "0")),
            held=str(wallet.get("held", "0")),
            balance_cny=_opt_str(wallet.get("balance_cny")),
            held_cny=_opt_str(wallet.get("held_cny")),
            credits_per_cny=_opt_str(wallet.get("credits_per_cny")),
        ),
    )


# ---------------------------------------------------------------- SaaS recharge (CNY)


class RechargeOrderRequest(BaseModel):
    amount_cny: str = Field(min_length=1, max_length=16)
    channel: Literal["wechat", "alipay"]


async def _recharge_proxy(request: Request, method: str, path: str, body: dict | None = None):
    if not is_saas():
        raise HTTPException(status_code=404, detail="recharge is only available in saas mode")
    from saas.adapter.control_plane_client import control_plane_user_request

    try:
        return await control_plane_user_request(
            method, path, access_token=_bearer_token(request), json_body=body
        )
    except ControlPlaneError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 503
        raise HTTPException(status_code=status, detail=exc.detail) from exc


@router.get("/me/recharge/options")
async def recharge_options(request: Request, _user: CurrentUser):
    """SaaS：充值档位、金额范围、可用渠道（人民币）。"""
    return await _recharge_proxy(request, "GET", "/v1/pay/options")


@router.post("/me/recharge/orders", status_code=201)
async def recharge_create_order(request: Request, body: RechargeOrderRequest, _user: CurrentUser):
    """SaaS：创建充值订单；微信返回二维码，支付宝返回支付页地址。"""
    return await _recharge_proxy(
        request, "POST", "/v1/pay/orders", {"amount_cny": body.amount_cny, "channel": body.channel}
    )


@router.get("/me/recharge/orders")
async def recharge_list_orders(request: Request, _user: CurrentUser):
    return await _recharge_proxy(request, "GET", "/v1/pay/orders")


@router.get("/me/recharge/orders/{order_no}")
async def recharge_get_order(order_no: str, request: Request, _user: CurrentUser):
    """SaaS：订单状态；待支付订单由控制面向支付平台查单（无需回调也能入账）。"""
    if not order_no.isalnum() or len(order_no) > 32:
        raise HTTPException(status_code=404, detail="order not found")
    return await _recharge_proxy(request, "GET", f"/v1/pay/orders/{order_no}")
