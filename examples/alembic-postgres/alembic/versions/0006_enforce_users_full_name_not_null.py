"""ENFORCE: users.full_name NOT NULL without a long ACCESS EXCLUSIVE scan

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-06 09:50:00

Plain `ALTER COLUMN SET NOT NULL` scans the whole table under ACCESS EXCLUSIVE.
Instead (PostgreSQL 12+):
  1. ADD CONSTRAINT ... CHECK (full_name IS NOT NULL) NOT VALID
       brief ACCESS EXCLUSIVE; no scan; enforced for new/updated rows
  2. VALIDATE CONSTRAINT
       scans the table under SHARE UPDATE EXCLUSIVE (reads and writes continue)
  3. SET NOT NULL
       skips the scan because a validated CHECK proves it (PG 12+)
  4. DROP CONSTRAINT the now-redundant check

Precondition: 0005 finished and the app writes full_name on every insert/update.
If VALIDATE fails (rows with NULL), the revision rolls back (transactional DDL);
fix the rows and re-run.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHECK_NAME = "ck_users_full_name_not_null"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE app.users ADD CONSTRAINT {CHECK_NAME} "
        "CHECK (full_name IS NOT NULL) NOT VALID"
    )
    op.execute(f"ALTER TABLE app.users VALIDATE CONSTRAINT {CHECK_NAME}")
    op.alter_column("users", "full_name", nullable=False, schema="app")
    op.execute(f"ALTER TABLE app.users DROP CONSTRAINT {CHECK_NAME}")


def downgrade() -> None:
    op.alter_column("users", "full_name", nullable=True, schema="app")
