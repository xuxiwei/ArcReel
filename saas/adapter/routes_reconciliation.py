"""SaaS: the workbench settings page reads the control plane's reconciliation reports.

Platform admins only (router dependency ``SAAS_ADMIN_ONLY``); the call is forwarded with the admin's own
control-plane token, which ``require_admin`` on the control plane accepts. 404 when self-hosted.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request

from saas.adapter.mode import is_saas

router = APIRouter(prefix="/saas/admin/reconciliation", tags=["SaaS 对账"])


def _token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


async def _forward(request: Request, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
    if not is_saas():
        raise HTTPException(status_code=404, detail="reconciliation is only available in saas mode")
    from saas.adapter.control_plane_client import ControlPlaneError, control_plane_user_request

    query = {k: v for k, v in (params or {}).items() if v is not None}
    url = f"/v1/admin/reconciliation{path}" + (f"?{urlencode(query)}" if query else "")
    try:
        return await control_plane_user_request(method, url, access_token=_token(request))
    except ControlPlaneError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 503
        raise HTTPException(status_code=status, detail=exc.detail) from exc


@router.get("")
async def list_reports(request: Request, limit: int = Query(30, ge=1, le=366)) -> Any:
    return await _forward(request, "GET", "", {"limit": limit})


@router.get("/{report_date}")
async def get_report(request: Request, report_date: date) -> Any:
    return await _forward(request, "GET", f"/{report_date.isoformat()}")


@router.post("/run")
async def run_internal(request: Request, report_date: date | None = None) -> Any:
    return await _forward(request, "POST", "/run", {"report_date": report_date.isoformat() if report_date else None})


@router.post("/statements/run")
async def run_statements(request: Request, report_date: date | None = None) -> Any:
    return await _forward(
        request, "POST", "/statements/run", {"report_date": report_date.isoformat() if report_date else None}
    )
