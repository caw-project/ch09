"""Unique display names and per-user preferences (register D46, D28).

Adds `users.display_name_key` — `names.name_key(display_name)` — under a unique
index, and the `user_preferences` table. Before the index can exist the data has
to satisfy it, so the upgrade first normalises every stored name (trim + NFC) and
renames every duplicate but the oldest (`names.deduplicate`: `Sam`, `Sam 2`, …).
Deleted accounts count: they keep their names, so they take part.

It imports `auth.names` on purpose — the issue wants the migration to apply *the
same code* as a rename (Req 4). The cost: a later change to that module changes
what a fresh install's 0002 does, and so what an install that already ran it
never sees.

The table is locked `SHARE ROW EXCLUSIVE` first, so a first sign-in waits instead
of inserting a duplicate between the read and the index.

During a rolling deploy the chart's `pre-upgrade` migrate Job (templates/auth/
migrate-job.yaml) runs this before the new pods start. An Auth pod still on the
old code then fails a first sign-in (no `display_name_key`, which is NOT NULL)
and could write a rename without its key, until it is replaced. The SPA on `main`
never renames, so the window is a first sign-in only.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20
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
    bind = op.get_bind()
    # New first sign-ins wait here, so none can insert a duplicate between the read and the index.
    op.execute("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE")
    op.add_column("users", sa.Column("display_name_key", sa.String(), nullable=True))

    rows = bind.execute(sa.text("SELECT id, display_name, email, created_at FROM users")).all()
    stored = [names.StoredName(*row) for row in rows]
    renamed = names.deduplicate(stored)

    for row in stored:
        new_name = renamed.get(row.id)
        if new_name is not None:
            bind.execute(
                sa.text(
                    "UPDATE users SET display_name = :name, updated_at = now(), "
                    "version = version + 1 WHERE id = :id"
                ),
                {"name": new_name, "id": row.id},
            )
        bind.execute(
            sa.text("UPDATE users SET display_name_key = :key WHERE id = :id"),
            {"key": names.name_key(new_name or row.display_name), "id": row.id},
        )

    op.alter_column("users", "display_name_key", nullable=False)
    op.create_index("uq_users_display_name_key", "users", ["display_name_key"], unique=True)

    op.create_table(
        "user_preferences",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("prefs", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Drop the table, the index and the column.

    One-way for the data: names that were trimmed, normalised or suffixed stay
    as the upgrade left them (Req 4).
    """
    op.drop_table("user_preferences")
    op.drop_index("uq_users_display_name_key", table_name="users")
    op.drop_column("users", "display_name_key")
