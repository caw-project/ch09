"""The `assets` table.

One row per uploaded file. The bytes are in object storage under
`{workspace_id}/attachment/{id}` — no file name, so nothing a user chose reaches
a key — and this row is everything else.

**`message_id` and `claimed_at` are the claim** (issue 4, decision 9). Messaging
claims an asset for a message it is about to insert; the claim locks the row
`FOR UPDATE`, so two sends racing for one asset serialize. A claim is the only
way a download URL is ever minted.

No foreign key on `workspace_id`, `owner_id` or `message_id`: they name rows in
Auth's and Messaging's databases (Conventions §2).

`deleted_at` is present because Conventions §3 expects it and every select
filters it, though nothing deletes an asset yet (register D16, still open).

Revision ID: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMPTZ = TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("bucket", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.Column("message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("confirmed_at", TIMESTAMPTZ, nullable=True),
        sa.Column("claimed_at", TIMESTAMPTZ, nullable=True),
        sa.Column("deleted_at", TIMESTAMPTZ, nullable=True),
        sa.UniqueConstraint("bucket", "object_key"),
    )


def downgrade() -> None:
    op.drop_table("assets")
