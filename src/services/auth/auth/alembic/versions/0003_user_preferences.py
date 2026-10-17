"""Per-user preferences (gh-3, register D28).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMPTZ = TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("prefs", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
