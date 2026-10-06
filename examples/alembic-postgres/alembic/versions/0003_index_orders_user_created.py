"""index orders (user_id, created_at) concurrently

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-06 09:20:00

Serves: "latest orders for a user" (WHERE user_id = $1 ORDER BY created_at DESC).
Tradeoff: faster reads for that pattern; extra storage and write cost on every
INSERT/UPDATE of orders.

CREATE INDEX CONCURRENTLY cannot run inside a transaction block, so it runs
inside op.get_context().autocommit_block(). Only SHARE UPDATE EXCLUSIVE is
taken (writes continue). If the build fails it leaves an INVALID index:
drop it (DROP INDEX CONCURRENTLY) and re-run the migration.

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_orders_user_id_created_at",
            "orders",
            ["user_id", "created_at"],
            schema="app",
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_orders_user_id_created_at",
            table_name="orders",
            schema="app",
            postgresql_concurrently=True,
        )
