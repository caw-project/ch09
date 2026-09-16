"""Reactions.

One row per person per emoji per message, and **the composite primary key is the
concurrency control**. Adding is `ON CONFLICT DO NOTHING` and removing is a plain
`DELETE`, so a double-click, a retried request and two tabs racing all converge
on the same state with no version column and nothing to conflict on — the same
argument `0003` makes for the forward-only read marker.

Three columns the conventions would expect are absent on purpose:

* **No `deleted_at`.** Removing a reaction is a real delete: there is no history
  requirement, nothing renders a removed reaction, and a tombstone here would be
  a row nobody may ever read. Conventions §3's soft-delete rule does not apply to
  a table without the column.
* **No `version`.** See the primary key above.
* **No foreign key on `user_id`.** Users are Auth's rows (Conventions §2).
  `message_id` gets a real one — both ends are ours — and it cascades, so a
  future retention job that hard-deletes a message (register D16) cannot strand
  a reaction behind it.

No index beyond the primary key. Every read groups by `message_id`, which leads
the key, so the primary key index serves it.

Revision ID: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMPTZ = TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "message_reactions",
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("emoji", sa.String(32), primary_key=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("message_reactions")
