"""SaaS: give pre-SaaS global assets (``assets.org_id = ''``) to one organisation.

Assets created before the library became per-organisation have no owner, so no organisation sees them.
Run once after migrating an old database::

    python -m saas.isolation.assign_legacy_assets --org <org_id>           # dry run: what would move
    python -m saas.isolation.assign_legacy_assets --org <org_id> --apply   # move them

An entry whose type and name already exist in the target organisation is skipped (names are unique per
organisation) and listed, so nothing is overwritten. Files stay where they are; the media route serves
them to the new owner because it looks the path up through ``assets.org_id``.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field

from sqlalchemy import select, update

from lib.db.models.asset import Asset

LEGACY_ORG = ""


@dataclass
class Plan:
    move: list[tuple[str, str, str]] = field(default_factory=list)  # (id, type, name)
    conflicts: list[tuple[str, str, str]] = field(default_factory=list)


async def plan_assignment(session, org_id: str) -> Plan:
    taken = set(
        (await session.execute(select(Asset.type, Asset.name).where(Asset.org_id == org_id))).tuples().all()
    )
    plan = Plan()
    rows = await session.execute(
        select(Asset.id, Asset.type, Asset.name).where(Asset.org_id == LEGACY_ORG).order_by(Asset.type, Asset.name)
    )
    for asset_id, asset_type, name in rows.tuples():
        target = plan.conflicts if (asset_type, name) in taken else plan.move
        target.append((asset_id, asset_type, name))
    return plan


async def apply_assignment(session, org_id: str, plan: Plan) -> int:
    ids = [asset_id for asset_id, _, _ in plan.move]
    if not ids:
        return 0
    result = await session.execute(
        update(Asset).where(Asset.id.in_(ids), Asset.org_id == LEGACY_ORG).values(org_id=org_id)
    )
    await session.commit()
    return int(result.rowcount or 0)


async def _main(org_id: str, apply: bool) -> None:
    from lib.db import async_session_factory

    async with async_session_factory() as session:
        plan = await plan_assignment(session, org_id)
        print(f"legacy assets to move: {len(plan.move)}; skipped (name already used in org): {len(plan.conflicts)}")
        for _, asset_type, name in plan.conflicts:
            print(f"  skip {asset_type}/{name}")
        if not apply:
            print("dry run: add --apply to move them")
            return
        moved = await apply_assignment(session, org_id, plan)
        print(f"moved {moved} assets to org {org_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--org", required=True, help="target organisation id (control-plane org id)")
    parser.add_argument("--apply", action="store_true", help="actually move the assets")
    args = parser.parse_args()
    if not args.org.strip():
        parser.error("--org must not be empty")
    asyncio.run(_main(args.org.strip(), args.apply))


if __name__ == "__main__":
    main()
