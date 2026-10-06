"""BACKFILL: copy users.name into users.full_name in batches

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-06 09:40:00

Each batch commits on its own (autocommit_block), so row locks are held only for
one batch and WAL/replication lag stays bounded. One giant UPDATE would hold row
locks until commit, bloat the table with dead tuples, and may hit statement_timeout.
The loop is idempotent: it only touches rows where full_name IS NULL, so a failed
run can simply be re-run. For very large tables run this as a separate job
(see production-migrations.md) instead of inside the deploy.

Batch selection is by primary key so each UPDATE is an index-driven scan.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BATCH_SIZE = 1000

BACKFILL_BATCH = sa.text(
    """
    UPDATE app.users
       SET full_name = name
     WHERE id IN (
           SELECT id FROM app.users
            WHERE full_name IS NULL
            ORDER BY id
            LIMIT :batch_size
            FOR UPDATE SKIP LOCKED
     )
    """
)


def upgrade() -> None:
    if op.get_context().as_sql:
        # Offline mode (--sql) cannot run a loop that reads rowcount.
        op.execute("-- 0005: batched backfill not rendered offline; run it online")
        return
    bind = op.get_bind()
    with op.get_context().autocommit_block():
        while True:
            result = bind.execute(BACKFILL_BATCH, {"batch_size": BATCH_SIZE})
            if result.rowcount == 0:
                break


def downgrade() -> None:
    # Data copy only; nothing structural to undo. 0004's downgrade drops the column.
    pass
