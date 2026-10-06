"""EXPAND: add nullable users.full_name (rename users.name in 4 steps)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-06 09:30:00

Expand/contract rename of users.name -> users.full_name:

  0004 expand    add nullable full_name        (this revision; old app still works)
  deploy         new app dual-writes name + full_name, reads full_name
  0005 backfill  copy name -> full_name in batches
  0006 enforce   NOT NULL on full_name via NOT VALID check -> VALIDATE -> SET NOT NULL
  deploy         app stops writing name
  0007 contract  drop name                     (DESTRUCTIVE; separate release)

Never `ALTER TABLE ... RENAME COLUMN` on a live table: old app instances break
the moment it commits.

Lock note: ADD COLUMN without a default is metadata-only (brief ACCESS EXCLUSIVE).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("full_name", sa.String(length=200), nullable=True), schema="app"
    )


def downgrade() -> None:
    # Safe while name is still the source of truth (before 0007).
    op.drop_column("users", "full_name", schema="app")
