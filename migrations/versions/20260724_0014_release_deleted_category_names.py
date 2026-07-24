"""Release unique names held by previously tombstoned budget categories.

Revision ID: 20260724_0014
Revises: 20260724_0013
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0014"
down_revision = "20260724_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Free reusable names without deleting categories or their relationships."""

    connection = op.get_bind()
    categories = sa.table(
        "budget_categories",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String(length=100)),
    )
    tombstones = sa.table(
        "record_tombstones",
        sa.column("entity_type", sa.String(length=100)),
        sa.column("entity_id", sa.Integer()),
    )
    rows = connection.execute(
        sa.select(categories.c.id, categories.c.name)
        .select_from(
            categories.join(
                tombstones,
                sa.and_(
                    tombstones.c.entity_type == "budget_categories",
                    tombstones.c.entity_id == categories.c.id,
                ),
            )
        )
        .order_by(categories.c.id)
    ).all()
    occupied_names = set(connection.execute(sa.select(categories.c.name)).scalars())

    for category_id, current_name in rows:
        base_name = f"__lv_deleted_budget_categories_{category_id}"
        replacement = base_name
        suffix = 1
        while replacement in occupied_names and replacement != current_name:
            suffix += 1
            replacement = f"{base_name}_{suffix}"
        if replacement == current_name:
            continue
        connection.execute(
            sa.update(categories).where(categories.c.id == category_id).values(name=replacement)
        )
        occupied_names.discard(current_name)
        occupied_names.add(replacement)


def downgrade() -> None:
    """Keep names released because original values remain in tombstone snapshots."""
