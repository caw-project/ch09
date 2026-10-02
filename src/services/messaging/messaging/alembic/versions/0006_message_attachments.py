"""Message attachments, and the array column they replace.

`message_attachments` is a **snapshot** of what the Asset service said about each
asset when the message claimed it: file name, content type and size. Reading a
page of history then costs one grouped query here and never a call to Asset, and
the chip a message shows cannot change under it. The bytes and the download URL
stay Asset's.

* **Keyed on `(message_id, position)`**, where `position` is the attach order,
  0-based — the order the sender chose is the order everyone sees.
* **`asset_id` is `UNIQUE`**: a second guard behind Asset's claim, and what
  refuses the same id twice in one send. No foreign key on it — an asset is
  Asset's row, in Asset's database (Conventions §2). `message_id` gets a real one
  that cascades, so a future retention job (register D16) that hard-deletes a
  message cannot strand its attachments.

`messages.attachments uuid[]` is dropped in the same step. Nothing ever wrote to
it — every row holds `'{}'` — and a column that says "attachments" while the real
ones live in another table is a trap.

Revision ID: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_attachments",
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("asset_id", UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("message_id", "position"),
        sa.UniqueConstraint("asset_id"),
    )
    op.drop_column("messages", "attachments")


def downgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "attachments",
            ARRAY(UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.drop_table("message_attachments")
