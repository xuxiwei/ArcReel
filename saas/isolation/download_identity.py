"""SaaS: one-off download links (project export ZIP, Jianying draft) resolve the project in the
organisation that issued them.

Those two routes authenticate with a short-lived ``download_token`` in the query string instead of a
Bearer header, so no billing identity is bound and ``get_project_manager()`` falls back to the flat
data root — in SaaS the project then looks missing. The token now also carries the issuer's ``org`` and
``uid`` (``server.auth.create_download_token``), and :func:`bind_download_identity`, mounted as a
router-level dependency (it runs before the route's own service dependencies), binds that identity.

The route still verifies the token itself exactly as upstream does; this dependency never rejects.
Self-hosted: no-op.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from saas.adapter.mode import is_saas


def tenant_claims() -> dict[str, Any]:
    if not is_saas():
        return {}
    from saas.adapter.billing_context import get_billing_identity

    identity = get_billing_identity()
    if identity is None:
        return {}
    return {"org": identity.org_id, "uid": identity.user_id}


async def bind_download_identity(request: Request) -> None:
    if not is_saas():
        return
    token = request.query_params.get("download_token")
    project_name = request.path_params.get("name") or request.path_params.get("project_name")
    if not token or not project_name:
        return
    from server.auth import verify_download_token

    try:
        payload = verify_download_token(token, project_name)
    except Exception:
        return  # the route answers 401/403 itself
    org_id, user_id = payload.get("org"), payload.get("uid")
    if not isinstance(org_id, str) or not isinstance(user_id, str):
        return
    from saas.adapter.billing_context import BillingIdentity, set_billing_identity
    from saas.isolation.paths import safe_org_segment

    try:
        safe_org_segment(org_id)
    except ValueError:
        return
    set_billing_identity(BillingIdentity(user_id=user_id, org_id=org_id))
