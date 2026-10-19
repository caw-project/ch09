"""Migration 0002: unique names and the preferences table (issue gh-3, Req 4).

Each test gets a database of its own, migrated to `0001` — the schema as it was
when nothing stopped two accounts holding the same name — seeded in SQL, and then
upgraded to head. Seeded `created_at`s are spread so that "oldest" and "smallest
id" disagree: a migration that ordered by id would keep the wrong account.

The fixture is **synchronous**: `service_database` runs `asyncio.run` itself, so it
cannot be called from inside an async test.

Characters that are awkward to read are built with `chr()`: the lint hook rewrites
a `\\u` escape into the raw character.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from functools import partial

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from auth.migrations import upgrade_to
from testkit.databases import PostgresServer, service_database

E_ACUTE = chr(0xE9)
E_ACUTE_UPPER = chr(0xC9)
COMBINING_ACUTE = chr(0x301)


def at(month: int) -> datetime:
    return datetime(2026, month, 1, tzinfo=UTC)


def uid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


@pytest.fixture
def at_0001(postgres_server: PostgresServer) -> str:
    name = f"auth_mig_{uuid.uuid4().hex[:8]}"
    return service_database(postgres_server, name, partial(upgrade_to, revision="0001"))


async def seed(dsn: str, rows: list[tuple[uuid.UUID, str, datetime, datetime | None]]) -> None:
    engine = create_async_engine(dsn)
    try:
        async with engine.begin() as connection:
            for n, (user_id, name, created_at, deleted_at) in enumerate(rows):
                await connection.execute(
                    text(
                        "INSERT INTO users (id, email, display_name, created_at, deleted_at) "
                        "VALUES (:id, :email, :name, :created_at, :deleted_at)"
                    ),
                    {
                        "id": user_id,
                        "email": f"user{n}@example.com",
                        "name": name,
                        "created_at": created_at,
                        "deleted_at": deleted_at,
                    },
                )
    finally:
        await engine.dispose()


async def migrate(dsn: str) -> dict[uuid.UUID, tuple[str, str]]:
    """Upgrade to head, and read back `{id: (display_name, display_name_key)}`."""
    await upgrade_to(dsn, "head")
    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT id, display_name, display_name_key FROM users")
            )
            return {row.id: (row.display_name, row.display_name_key) for row in result}
    finally:
        await engine.dispose()


async def test_stored_names_are_trimmed_and_composed(at_0001: str) -> None:
    await seed(
        at_0001,
        [
            (uid(1), "  Ada  ", at(1), None),
            (uid(2), "Jose" + COMBINING_ACUTE, at(2), None),
            (uid(3), "Grace", at(3), None),
        ],
    )

    names = await migrate(at_0001)

    assert names[uid(1)] == ("Ada", "ada")
    assert names[uid(2)] == ("Jos" + E_ACUTE, "jos" + E_ACUTE)
    # A name that was already fine is not touched.
    assert names[uid(3)] == ("Grace", "grace")


async def test_duplicates_are_renamed_except_the_oldest(at_0001: str) -> None:
    # The oldest account has the *largest* id, so ordering by id keeps the wrong one.
    await seed(
        at_0001,
        [
            (uid(3), "Sam", at(1), None),
            (uid(1), "sam", at(2), None),
            (uid(2), "SAM", at(3), None),
        ],
    )

    names = await migrate(at_0001)

    assert names[uid(3)][0] == "Sam"
    assert names[uid(1)][0] == "sam 2"
    assert names[uid(2)][0] == "SAM 3"
    assert len({key for _, key in names.values()}) == 3


async def test_duplicates_only_normalising_reveals(at_0001: str) -> None:
    await seed(
        at_0001,
        [
            (uid(1), "Jos" + E_ACUTE, at(1), None),
            (uid(2), " JOSE" + COMBINING_ACUTE, at(2), None),
        ],
    )

    names = await migrate(at_0001)

    assert names[uid(1)][0] == "Jos" + E_ACUTE
    assert names[uid(2)][0] == "JOS" + E_ACUTE_UPPER + " 2"


async def test_a_deleted_account_counts_as_the_oldest(at_0001: str) -> None:
    await seed(
        at_0001,
        [
            (uid(1), "Sam", at(1), at(5)),
            (uid(2), "sam", at(2), None),
        ],
    )

    names = await migrate(at_0001)

    assert names[uid(1)][0] == "Sam"
    assert names[uid(2)][0] == "sam 2"


async def test_a_suffix_another_row_holds_is_skipped(at_0001: str) -> None:
    await seed(
        at_0001,
        [
            (uid(1), "Sam", at(1), None),
            (uid(2), "Sam", at(2), None),
            (uid(3), "Sam 2", at(3), None),
        ],
    )

    names = await migrate(at_0001)

    assert names[uid(1)][0] == "Sam"
    assert names[uid(2)][0] == "Sam 3"
    assert names[uid(3)][0] == "Sam 2"


async def test_an_empty_name_becomes_user(at_0001: str) -> None:
    await seed(at_0001, [(uid(1), "   ", at(1), None), (uid(2), "Ada", at(2), None)])

    names = await migrate(at_0001)

    assert names[uid(1)] == ("user", "user")
    assert names[uid(2)] == ("Ada", "ada")


async def test_the_index_refuses_a_duplicate_afterwards(at_0001: str) -> None:
    await seed(at_0001, [(uid(1), "Ada", at(1), None)])
    await migrate(at_0001)

    insert = text(
        "INSERT INTO users (id, email, display_name, display_name_key) "
        "VALUES (:id, :email, :name, :key)"
    )
    engine = create_async_engine(at_0001)
    try:
        async with engine.begin() as connection:
            # A different key is fine: the index is not refusing everything.
            await connection.execute(
                insert, {"id": uid(2), "email": "b@example.com", "name": "Grace", "key": "grace"}
            )
        with pytest.raises(IntegrityError) as caught:
            async with engine.begin() as connection:
                await connection.execute(
                    insert, {"id": uid(3), "email": "c@example.com", "name": "ADA", "key": "ada"}
                )
    finally:
        await engine.dispose()

    assert "ux_users_display_name_key" in str(caught.value)


async def test_the_preferences_table_is_created_empty_and_tied_to_users(at_0001: str) -> None:
    await seed(at_0001, [(uid(1), "Ada", at(1), None)])
    await migrate(at_0001)

    engine = create_async_engine(at_0001)
    try:
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM user_preferences")) == 0
            await connection.execute(
                text("INSERT INTO user_preferences (user_id) VALUES (:id)"), {"id": uid(1)}
            )
            row = (
                await connection.execute(text("SELECT prefs, version FROM user_preferences"))
            ).one()
            assert (row.prefs, row.version) == ({}, 0)
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text("INSERT INTO user_preferences (user_id) VALUES (:id)"), {"id": uid(99)}
                )
    finally:
        await engine.dispose()
