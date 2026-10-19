"""Unique display names and per-user preferences (register D46, D28).

Existing names are made unique first, by the same `names.dedupe` the sign-in and
rename paths are held to: every stored name is trimmed and NFC-composed, and where
two accounts hold the same name once case and form are ignored, the oldest keeps
it and the rest take `<name> 2`, `<name> 3`, …. Deleted accounts count — their
names stay taken. Then the key column is filled, made NOT NULL and put under a
unique index that is deliberately not partial.

One-way: the renamed names are not restored by `downgrade`.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from auth import names

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMPTZ = TIMESTAMP(timezone=True)


def upgrade() -> None:
    connection = op.get_bind()
    op.add_column("users", sa.Column("display_name_key", sa.String(), nullable=True))

    rows = connection.execute(
        sa.text("SELECT id, display_name FROM users ORDER BY created_at, id")
    ).all()
    changed = names.dedupe([(row.id, row.display_name) for row in rows])
    for user_id, name in changed.items():
        connection.execute(
            sa.text("UPDATE users SET display_name = :name WHERE id = :id"),
            {"name": name, "id": user_id},
        )

    for row in rows:
        stored = changed.get(row.id, row.display_name)
        connection.execute(
            sa.text("UPDATE users SET display_name_key = :key WHERE id = :id"),
            {"key": names.name_key(stored), "id": row.id},
        )

    op.alter_column("users", "display_name_key", nullable=False)
    op.create_index("ux_users_display_name_key", "users", ["display_name_key"], unique=True)

    op.create_table(
        "user_preferences",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("prefs", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
    op.drop_index("ux_users_display_name_key", table_name="users")
    op.drop_column("users", "display_name_key")
