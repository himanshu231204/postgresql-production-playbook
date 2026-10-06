"""add orders.currency with a constant default

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-06 09:10:00

Lock note (PostgreSQL 11+): ADD COLUMN with a constant (non-volatile) DEFAULT
is metadata-only: no table rewrite. It still takes ACCESS EXCLUSIVE briefly, so
lock_timeout (set in env.py) prevents queueing behind a long transaction.
A volatile default (e.g. random(), clock_timestamp()) forces a full rewrite.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'USD'"), nullable=False),
        schema="app",
    )


def downgrade() -> None:
    # DESTRUCTIVE: discards currency values.
    op.drop_column("orders", "currency", schema="app")
