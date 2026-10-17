"""Unique display names — a stored comparison key, a unique index (gh-3, D46).

The key is computed by `auth.names`, never by SQL, so the database compares
exactly what the application will compute on every later write. Existing names
are tidied (trim + NFC) and duplicates renamed with the same code the rename
route and the first sign-in use; the oldest account of each key keeps its name.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from auth import names

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("users", sa.Column("display_name_key", sa.String(), nullable=True))

    # conventions: ok — deleted rows are read on purpose: names stay taken after
    # deletion (D46, Conventions §3's third soft-delete exception).
    rows = bind.execute(
        sa.text("SELECT id, display_name, email FROM users ORDER BY created_at, id")
    ).all()
    for user_id, name in names.dedupe([(r[0], r[1], r[2]) for r in rows]).items():
        bind.execute(
            sa.text("UPDATE users SET display_name = :n, display_name_key = :k WHERE id = :id"),
            {"n": name, "k": names.name_key(name), "id": user_id},
        )

    op.alter_column("users", "display_name_key", nullable=False)
    op.create_index("ux_users_display_name_key", "users", ["display_name_key"], unique=True)


def downgrade() -> None:
    # The renamed names stay renamed: there is no record of what they were.
    op.drop_index("ux_users_display_name_key", table_name="users")
    op.drop_column("users", "display_name_key")
