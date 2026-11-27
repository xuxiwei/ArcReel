"""SaaS: global asset library per organisation (assets.org_id, names unique per org)

Revision ID: 5a1e0c7d9b42
Revises: 2d4a9f6c8b31
Create Date: 2026-11-27

``org_id`` is ``""`` for self-hosted rows (and for rows created before this migration); uniqueness
moves from ``(type, name)`` to ``(org_id, type, name)``. See saas/patches/asset-library-org.md.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5a1e0c7d9b42"
down_revision: str | Sequence[str] | None = "2d4a9f6c8b31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("assets", schema=None) as batch_op:
        batch_op.add_column(sa.Column("org_id", sa.String(length=64), nullable=False, server_default=""))
        batch_op.drop_constraint("uq_asset_type_name", type_="unique")
        batch_op.create_unique_constraint("uq_asset_org_type_name", ["org_id", "type", "name"])
        batch_op.create_index("ix_asset_org_id", ["org_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("assets", schema=None) as batch_op:
        batch_op.drop_index("ix_asset_org_id")
        batch_op.drop_constraint("uq_asset_org_type_name", type_="unique")
        batch_op.create_unique_constraint("uq_asset_type_name", ["type", "name"])
        batch_op.drop_column("org_id")
