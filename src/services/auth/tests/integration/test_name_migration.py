"""Migration 0002 on data that already exists (issue gh-3, Req 4).

The tests are synchronous because each builds a database of its own at revision
0001, seeds rows the old schema allowed (duplicates, untrimmed names, an empty
one), and only then runs the rest of the history. A table-truncating fixture on
the shared database could never show what the migration does to existing rows.

The change is one-way, so what it must not touch matters as much as what it
renames: rows that need nothing keep their `version`.
"""

from __future__ import annotations

import asyncio
import itertools
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from alembic import command
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from auth.migrations import alembic_config, upgrade_to_head
from testkit.databases import PostgresServer, service_database

T0 = datetime(2026, 1, 1, tzinfo=UTC)
_databases = itertools.count(1)

E_ACUTE = chr(0x00E9)
CAPITAL_E_ACUTE = chr(0x00C9)
COMBINING_ACUTE = chr(0x0301)


def _to_0001(connection: Connection, dsn: str) -> None:
    config = alembic_config(dsn)
    config.attributes["connection"] = connection
    command.upgrade(config, "0001")


async def to_0001(dsn: str) -> None:
    engine = create_async_engine(dsn)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_to_0001, dsn)
    finally:
        await engine.dispose()


def old_database(postgres_server: PostgresServer) -> str:
    """A fresh database holding only what revision 0001 created."""
    return service_database(postgres_server, f"auth_mig_{next(_databases)}", to_0001)


def user(n: int, name: str, *, age: int, email: str | None = None, deleted: bool = False) -> dict:
    """A seed row; a lower `age` is an older account."""
    return {
        "id": uuid.UUID(int=n),
        "email": email or f"user{n}@example.com",
        "name": name,
        "created": T0 + timedelta(days=age),
        "deleted": T0 if deleted else None,
    }


async def _seed(dsn: str, rows: list[dict]) -> None:
    engine = create_async_engine(dsn)
    try:
        async with engine.begin() as connection:
            for r in rows:
                await connection.execute(
                    text(
                        "INSERT INTO users (id, email, display_name, created_at, deleted_at) "
                        "VALUES (:id, :email, :name, :created, :deleted)"
                    ),
                    r,
                )
    finally:
        await engine.dispose()


async def _read(dsn: str, sql: str) -> list[dict[str, Any]]:
    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as connection:
            return [dict(r) for r in (await connection.execute(text(sql))).mappings().all()]
    finally:
        await engine.dispose()


def migrate(postgres_server: PostgresServer, rows: list[dict]) -> tuple[str, dict[int, dict]]:
    """Seed revision 0001, run the rest, and return the users keyed by seed number."""
    dsn = old_database(postgres_server)
    asyncio.run(_seed(dsn, rows))
    asyncio.run(upgrade_to_head(dsn))
    stored = asyncio.run(_read(dsn, "SELECT * FROM users"))
    return dsn, {r["id"].int: r for r in stored}


def test_every_name_is_trimmed_and_nfc(postgres_server: PostgresServer) -> None:
    """Req 4 starts with the same normalisation as a rename; untouched rows are left alone."""
    _, users = migrate(
        postgres_server,
        [
            user(1, "  Ada  ", age=3),
            user(2, "Jose" + COMBINING_ACUTE, age=2),
            user(3, "Grace", age=1),
        ],
    )

    assert users[1]["display_name"] == "Ada"
    assert users[2]["display_name"] == "Jos" + E_ACUTE
    assert users[3]["display_name"] == "Grace"
    assert users[1]["version"] == 1
    assert users[2]["version"] == 1
    assert users[3]["version"] == 0, "a name that needed no change must not be touched"


def test_every_duplicate_but_the_oldest_is_renamed(postgres_server: PostgresServer) -> None:
    """The oldest keeps the name even though it is deleted: deleted accounts still hold theirs."""
    _, users = migrate(
        postgres_server,
        [
            user(1, "Sam", age=1, deleted=True),
            user(2, "Sam", age=2),
            user(3, "Sam", age=3),
        ],
    )

    assert users[1]["display_name"] == "Sam"
    assert users[2]["display_name"] == "Sam 2"
    assert users[3]["display_name"] == "Sam 3"
    assert users[1]["version"] == 0
    assert users[2]["version"] == 1
    assert users[3]["updated_at"] > users[1]["updated_at"]


def test_duplicates_only_normalising_reveals_are_renamed(postgres_server: PostgresServer) -> None:
    """` José ` and `JOSÉ` are different bytes in the old table and one name in the new."""
    _, users = migrate(
        postgres_server,
        [
            user(1, " Jos" + E_ACUTE + " ", age=1),
            user(2, "JOS" + CAPITAL_E_ACUTE, age=2),
        ],
    )

    assert users[1]["display_name"] == "Jos" + E_ACUTE
    assert users[2]["display_name"] == "JOS" + CAPITAL_E_ACUTE + " 2"


def test_an_empty_stored_name_takes_the_email_local_part(postgres_server: PostgresServer) -> None:
    """`PATCH` never trimmed, so a blank name can be stored; the sign-in fallback names it."""
    _, users = migrate(
        postgres_server,
        [user(1, "   ", age=1, email="grace@example.com"), user(2, "Ada", age=2)],
    )

    assert users[1]["display_name"] == "grace"


def test_after_the_migration_every_key_is_set_and_unique(postgres_server: PostgresServer) -> None:
    """The key column is filled for every row, indexed uniquely, and preferences can be stored."""
    dsn, users = migrate(
        postgres_server,
        [user(1, "Sam", age=1), user(2, "SAM", age=2), user(3, "Ada", age=3)],
    )

    assert {n: u["display_name_key"] for n, u in users.items()} == {
        1: "sam",
        2: "sam 2",
        3: "ada",
    }
    index = asyncio.run(
        _read(
            dsn,
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_users_display_name_key'",
        )
    )
    assert len(index) == 1
    assert "UNIQUE" in index[0]["indexdef"]
    table = asyncio.run(_read(dsn, "SELECT to_regclass('user_preferences')::text AS t"))
    assert table[0]["t"] == "user_preferences"
