"""add subscribed_since to subscriptions

Revision ID: c7d8e9f0a1b2
Revises: 9afad140d8a2
Create Date: 2026-06-09 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: str | Sequence[str] | None = "9afad140d8a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("subscribed_since", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "subscribed_since")
