"""The thread index.

`0002_messages` left `ix_messages_thread` out because nothing queried
`thread_root_id`. Threads do: the per-page reply summary and the replies page.

Partial, so top-level rows — almost all of the table — never enter it.
`(thread_root_id, id)` serves the summary aggregate and the replies page's keyset
alike. A plain `CREATE INDEX` rather than `CONCURRENTLY`: every environment is
pre-production and small; it is worth the `autocommit_block` only once the table
is big enough for the write lock to be noticed.

Revision ID: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_messages_thread",
        "messages",
        ["thread_root_id", "id"],
        postgresql_where=sa.text("thread_root_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_messages_thread", table_name="messages")
