"""Unique display names, and per-user preferences.

Order matters: clean, de-duplicate, and only then create the index that forbids
what was just fixed. Names are cleaned and de-duplicated by the same rules the
service applies at sign-in (`auth.names`), imported rather than copied so there
is one suffix rule. The rename is one-way: `downgrade` drops the index and the
table but does not restore the old names. No name is logged.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16
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


def _dedupe(bind: sa.engine.Connection) -> None:
    """Rename every name that is not unique, oldest account keeping its own."""
    rows = bind.execute(sa.text("SELECT id, display_name FROM users ORDER BY created_at, id")).all()
    cleaned = [(row.id, row.display_name, names.provisional_name(row.display_name)) for row in rows]

    # Names are compared the way the index folds them: Postgres `lower()`, not
    # Python's `str.lower()`. They differ (U+0130 is `i` in one and `i` + U+0307
    # in the other), and a pair only Postgres sees as equal would abort the index.
    folded: dict[str, str] = {}

    def fold(name: str) -> str:
        if name not in folded:
            folded[name] = bind.execute(
                sa.text("SELECT lower(CAST(:name AS varchar))"), {"name": name}
            ).scalar_one()
        return folded[name]

    # Every stored name is reserved first, so a suffix never takes a name an
    # account already holds and no one without a duplicate is renamed.
    reserved = {fold(name) for _, _, name in cleaned}
    assigned: set[str] = set()

    for user_id, stored, name in cleaned:
        final = name
        if fold(name) in assigned:
            final = next(
                candidate
                for candidate in names.candidates(name)
                if fold(candidate) not in reserved and fold(candidate) not in assigned
            )
        assigned.add(fold(final))
        if final != stored:
            bind.execute(
                sa.text("UPDATE users SET display_name = :name WHERE id = :id"),
                {"name": final, "id": user_id},
            )


def upgrade() -> None:
    _dedupe(op.get_bind())

    op.create_index("uq_users_display_name", "users", [sa.text("lower(display_name)")], unique=True)

    op.create_table(
        "user_preferences",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("prefs", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
    op.drop_index("uq_users_display_name", table_name="users")
