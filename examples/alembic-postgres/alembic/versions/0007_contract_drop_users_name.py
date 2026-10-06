"""CONTRACT: drop legacy users.name  (DESTRUCTIVE, irreversible data loss)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-06 10:00:00

Run only when ALL of these hold:
  - no running application version reads or writes users.name
    (verify: previous release fully drained; check pg_stat_activity / logs)
  - a verified backup or snapshot exists (see 07-backups-recovery/)
  - you are connected to the intended database (alembic current)
Safer alternative: leave the column for a full release cycle (or `ALTER ... DROP
NOT NULL` first) before dropping it.

Lock: ACCESS EXCLUSIVE, brief; the column is only marked dropped, not rewritten.
Downgrade re-creates the column and repopulates it from full_name (identical by
construction), so it is lossless only while the two columns have not diverged.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "name", schema="app")


def downgrade() -> None:
    op.add_column("users", sa.Column("name", sa.String(length=200), nullable=True), schema="app")
    op.execute("UPDATE app.users SET name = full_name")  # fine for small tables; batch otherwise
    op.alter_column("users", "name", nullable=False, schema="app")
