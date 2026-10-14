"""One direct message per pair of people.

A DM is a `kind='dm'` channel whose `name` is the pair key `dm:{low}:{high}`
(`messaging.dms`). This index is the uniqueness of a pair, and get-or-create's
`ON CONFLICT` names it. Partial on `kind = 'dm'`: channels and private channels
keep their own naming rules and may repeat a name.

No data to backfill — nothing could create a DM before.

Revision ID: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ux_channels_dm_pair",
        "channels",
        ["workspace_id", "name"],
        unique=True,
        postgresql_where=sa.text("kind = 'dm'"),
    )


def downgrade() -> None:
    op.drop_index("ux_channels_dm_pair", table_name="channels")
