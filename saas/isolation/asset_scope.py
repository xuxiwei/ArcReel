"""SaaS: the global asset library belongs to an organisation.

``assets.org_id`` records the owning organisation (``""`` when self-hosted). ``AssetRepository`` reads
and creates only inside :func:`current_asset_org`; derivatives hang off their asset and follow it.
Library files keep their random names under ``global_assets/<type>/``; the media route serves one only
when an asset (or derivative) of the viewer's organisation points at it
(:func:`asset_file_visible`).
"""

from __future__ import annotations

from typing import Any

from saas.adapter.mode import is_saas

SELF_HOSTED_ORG = ""


class AssetOrgUnavailable(RuntimeError):
    """SaaS write without a bound organisation (should not happen on authenticated paths)."""


def current_asset_org() -> str | None:
    """Self-hosted → ``""``. SaaS → the bound org id, or ``None`` when no identity is bound."""
    if not is_saas():
        return SELF_HOSTED_ORG
    from saas.adapter.billing_context import get_billing_identity

    identity = get_billing_identity()
    return identity.org_id if identity is not None else None


def org_for_create() -> str:
    org = current_asset_org()
    if org is None:
        raise AssetOrgUnavailable("asset library write without an organisation")
    return org


def scope_assets(stmt: Any) -> Any:
    from sqlalchemy import false

    from lib.db.models.asset import Asset

    org = current_asset_org()
    return stmt.where(false()) if org is None else stmt.where(Asset.org_id == org)


async def asset_file_visible(session: Any, rel_path: str, org_id: str) -> bool:
    from sqlalchemy import or_, select

    from lib.db.models.asset import Asset, AssetDerivative

    direct = select(Asset.id).where(
        Asset.org_id == org_id, or_(Asset.image_path == rel_path, Asset.audio_path == rel_path)
    )
    if (await session.execute(direct.limit(1))).first() is not None:
        return True
    derived = (
        select(AssetDerivative.id)
        .join(Asset, Asset.id == AssetDerivative.asset_id)
        .where(Asset.org_id == org_id, AssetDerivative.image_path == rel_path)
    )
    return (await session.execute(derived.limit(1))).first() is not None
