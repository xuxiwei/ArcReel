"""HTTP client for ArcReel control-plane auth / credits / keys endpoints."""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

import httpx


_DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class ControlPlaneError(Exception):
    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.retry_after = retry_after


def get_control_plane_base_url() -> str:
    from urllib.parse import urlparse

    url = os.environ.get("CONTROL_PLANE_URL", "").strip().rstrip("/")
    if not url:
        raise ControlPlaneError(
            503,
            "CONTROL_PLANE_URL is not configured",
        )
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    loopback = host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost")
    if parsed.scheme not in {"http", "https"}:
        raise ControlPlaneError(503, "CONTROL_PLANE_URL must use http or https")
    if not loopback and parsed.scheme != "https":
        raise ControlPlaneError(
            503,
            "CONTROL_PLANE_URL must use https outside loopback",
        )
    return url


def get_internal_token() -> str:
    token = (
        os.environ.get("CONTROL_PLANE_INTERNAL_TOKEN", "").strip()
        or os.environ.get("CONTROL_PLANE_ADMIN_TOKEN", "").strip()
    )
    if not token:
        raise ControlPlaneError(
            503,
            "CONTROL_PLANE_INTERNAL_TOKEN (or CONTROL_PLANE_ADMIN_TOKEN) is not configured",
        )
    return token


def _client() -> httpx.AsyncClient:
    # Windows Internet Settings proxies can hijack 127.0.0.1 and return empty 502.
    # Control-plane calls are server-side; never inherit the user/system proxy.
    return httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, trust_env=False)


def _plain(value: Decimal | str) -> str:
    """Decimal as plain digits: ``str(Decimal("1E+1"))`` is "1E+1", which is ambiguous on the wire."""
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _internal_headers() -> dict[str, str]:
    return {"X-Internal-Token": get_internal_token()}


def _client_ip_headers(client_ip: str | None) -> dict[str, str]:
    """Forward the browser's address so the control plane rate-limits per user, not per workbench.

    The control plane honours ``X-Forwarded-For`` only alongside a valid
    ``X-Internal-Token``; without a configured token nothing is forwarded.
    """
    ip = (client_ip or "").strip()
    if not ip:
        return {}
    try:
        token = get_internal_token()
    except ControlPlaneError:
        return {}
    return {"X-Internal-Token": token, "X-Forwarded-For": ip}


async def control_plane_login(*, username: str, password: str, client_ip: str | None = None) -> dict[str, Any]:
    base = get_control_plane_base_url()
    try:
        async with _client() as client:
            resp = await client.post(
                f"{base}/v1/auth/login",
                json={"username": username, "password": password},
                headers=_client_ip_headers(client_ip),
            )
    except httpx.HTTPError as exc:
        raise ControlPlaneError(503, "control plane unreachable") from exc
    return _parse_auth_response(resp)


async def control_plane_register(
    *,
    username: str,
    password: str,
    email: str | None = None,
    client_ip: str | None = None,
) -> dict[str, Any]:
    base = get_control_plane_base_url()
    body: dict[str, Any] = {"username": username, "password": password}
    if email:
        body["email"] = email
    try:
        async with _client() as client:
            resp = await client.post(f"{base}/v1/auth/register", json=body, headers=_client_ip_headers(client_ip))
    except httpx.HTTPError as exc:
        raise ControlPlaneError(503, "control plane unreachable") from exc
    return _parse_auth_response(resp)


async def control_plane_me(*, access_token: str) -> dict[str, Any]:
    base = get_control_plane_base_url()
    try:
        async with _client() as client:
            resp = await client.get(
                f"{base}/v1/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError as exc:
        raise ControlPlaneError(503, "control plane unreachable") from exc
    if resp.status_code >= 400:
        raise ControlPlaneError(resp.status_code, _detail_from_response(resp))
    try:
        return resp.json()
    except ValueError as exc:
        raise ControlPlaneError(502, "control plane returned non-JSON") from exc


def _parse_auth_response(resp: httpx.Response) -> dict[str, Any]:
    if resp.status_code >= 400:
        raise ControlPlaneError(
            resp.status_code,
            _detail_from_response(resp),
            retry_after=resp.headers.get("Retry-After"),
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise ControlPlaneError(502, "control plane returned non-JSON") from exc
    if not isinstance(data, dict):
        raise ControlPlaneError(502, "control plane returned non-object JSON")
    token = data.get("access_token")
    if not token:
        raise ControlPlaneError(502, "control plane response missing access_token")
    return data


def _detail_from_response(resp: httpx.Response) -> str:
    try:
        payload = resp.json()
    except ValueError:
        return resp.text or f"control plane HTTP {resp.status_code}"
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail:
        return detail
    return f"control plane HTTP {resp.status_code}"


def _parse_json_object(resp: httpx.Response) -> dict[str, Any]:
    if resp.status_code >= 400:
        raise ControlPlaneError(resp.status_code, _detail_from_response(resp))
    try:
        data = resp.json()
    except ValueError as exc:
        raise ControlPlaneError(502, "control plane returned non-JSON") from exc
    if not isinstance(data, dict):
        raise ControlPlaneError(502, "control plane returned non-object JSON")
    return data


async def control_plane_internal_hold(
    *,
    org_id: str,
    user_id: str | None,
    estimate_credits: Decimal | str,
    call_id: str | None = None,
    task_id: str | None = None,
    purpose: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = get_control_plane_base_url()
    body: dict[str, Any] = {
        "org_id": org_id,
        "estimate_credits": _plain(estimate_credits),
    }
    if user_id:
        body["user_id"] = user_id
    if call_id:
        body["call_id"] = call_id
    if task_id:
        body["task_id"] = task_id
    if purpose:
        body["purpose"] = purpose
    if meta is not None:
        body["meta"] = meta
    try:
        async with _client() as client:
            resp = await client.post(
                f"{base}/v1/internal/credits/hold",
                headers=_internal_headers(),
                json=body,
            )
    except httpx.HTTPError as exc:
        raise ControlPlaneError(503, "control plane unreachable") from exc
    return _parse_json_object(resp)


async def control_plane_internal_settle(
    *,
    org_id: str,
    actual_credits: Decimal | str,
    hold_id: str | None = None,
    call_id: str | None = None,
    provider_cost_amount: Decimal | str | None = None,
    provider_cost_currency: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    base = get_control_plane_base_url()
    body: dict[str, Any] = {
        "org_id": org_id,
        "actual_credits": _plain(actual_credits),
    }
    if hold_id:
        body["hold_id"] = hold_id
    if call_id:
        body["call_id"] = call_id
    if provider_cost_amount is not None:
        body["provider_cost_amount"] = _plain(provider_cost_amount)
        body["provider_cost_currency"] = provider_cost_currency
    if model:
        body["model"] = model
    try:
        async with _client() as client:
            resp = await client.post(
                f"{base}/v1/internal/credits/settle",
                headers=_internal_headers(),
                json=body,
            )
    except httpx.HTTPError as exc:
        raise ControlPlaneError(503, "control plane unreachable") from exc
    return _parse_json_object(resp)


async def control_plane_internal_release(
    *,
    org_id: str,
    hold_id: str | None = None,
    call_id: str | None = None,
) -> dict[str, Any]:
    base = get_control_plane_base_url()
    body: dict[str, Any] = {"org_id": org_id}
    if hold_id:
        body["hold_id"] = hold_id
    if call_id:
        body["call_id"] = call_id
    try:
        async with _client() as client:
            resp = await client.post(
                f"{base}/v1/internal/credits/release",
                headers=_internal_headers(),
                json=body,
            )
    except httpx.HTTPError as exc:
        raise ControlPlaneError(503, "control plane unreachable") from exc
    return _parse_json_object(resp)


async def control_plane_platform_keys() -> list[dict[str, Any]]:
    base = get_control_plane_base_url()
    try:
        async with _client() as client:
            resp = await client.get(
                f"{base}/v1/internal/platform-keys",
                headers=_internal_headers(),
            )
    except httpx.HTTPError as exc:
        raise ControlPlaneError(503, "control plane unreachable") from exc
    if resp.status_code >= 400:
        raise ControlPlaneError(resp.status_code, _detail_from_response(resp))
    try:
        data = resp.json()
    except ValueError as exc:
        raise ControlPlaneError(502, "control plane returned non-JSON") from exc
    if not isinstance(data, list):
        raise ControlPlaneError(502, "control plane returned non-list JSON")
    return [row for row in data if isinstance(row, dict)]


async def control_plane_internal_config(key: str) -> str:
    base = get_control_plane_base_url()
    try:
        async with _client() as client:
            resp = await client.get(
                f"{base}/v1/internal/config/{key}",
                headers=_internal_headers(),
            )
    except httpx.HTTPError as exc:
        raise ControlPlaneError(503, "control plane unreachable") from exc
    data = _parse_json_object(resp)
    value = data.get("value")
    if not isinstance(value, str):
        raise ControlPlaneError(502, "control plane config missing value")
    return value


async def control_plane_internal_release_by_calls(call_ids: list[str]) -> int:
    base = get_control_plane_base_url()
    try:
        async with _client() as client:
            resp = await client.post(
                f"{base}/v1/internal/credits/release-by-call",
                headers=_internal_headers(),
                json={"call_ids": call_ids},
            )
    except httpx.HTTPError as exc:
        raise ControlPlaneError(503, "control plane unreachable") from exc
    return int(_parse_json_object(resp).get("released") or 0)


async def control_plane_internal_release_stale(*, call_id_prefix: str, older_than_seconds: int) -> int:
    base = get_control_plane_base_url()
    try:
        async with _client() as client:
            resp = await client.post(
                f"{base}/v1/internal/credits/release-stale",
                headers=_internal_headers(),
                json={"call_id_prefix": call_id_prefix, "older_than_seconds": older_than_seconds},
            )
    except httpx.HTTPError as exc:
        raise ControlPlaneError(503, "control plane unreachable") from exc
    return int(_parse_json_object(resp).get("released") or 0)


async def control_plane_user_request(
    method: str, path: str, *, access_token: str, json_body: dict[str, Any] | None = None
) -> Any:
    """Forward one user-scoped call (the user's own control-plane JWT) and return its JSON."""
    base = get_control_plane_base_url()
    try:
        async with _client() as client:
            resp = await client.request(
                method,
                f"{base}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
                json=json_body,
            )
    except httpx.HTTPError as exc:
        raise ControlPlaneError(503, "control plane unreachable") from exc
    if resp.status_code >= 400:
        raise ControlPlaneError(resp.status_code, _detail_from_response(resp))
    try:
        return resp.json()
    except ValueError as exc:
        raise ControlPlaneError(502, "control plane returned non-JSON") from exc
