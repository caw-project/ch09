"""Migration 0002: unique display names (gh-3 Req 4; register D46).

A migration that rewrites data is proven on data, so each test builds the
database at revision 0001, inserts users, upgrades to 0002 and reads them back.
It has a database of its own (`auth_migration`): the other integration tests
share `auth` at head, and a downgrade there would pull the schema out from
under them.

Every test starts by going all the way down and back up to 0001, so none of
them depends on what an earlier one left behind.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from auth.migrations import alembic_config
from testkit.databases import PostgresServer, service_database

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
NFD_JOSE = "Jose" + chr(0x301)
NFC_JOSE = "Jos" + chr(0xE9)


def _alembic(connection: Connection, dsn: str, action: str, revision: str) -> None:
    config = alembic_config(dsn)
    config.attributes["connection"] = connection
    getattr(command, action)(config, revision)


async def alembic(dsn: str, action: str, revision: str) -> None:
    engine = create_async_engine(dsn)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_alembic, dsn, action, revision)
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def migration_dsn(postgres_server: PostgresServer) -> str:
    return service_database(
        postgres_server, "auth_migration", lambda dsn: alembic(dsn, "upgrade", "0001")
    )


@pytest.fixture
async def at_0001(migration_dsn: str) -> AsyncIterator[AsyncEngine]:
    """The database at revision 0001, empty."""
    await alembic(migration_dsn, "downgrade", "base")
    await alembic(migration_dsn, "upgrade", "0001")
    engine = create_async_engine(migration_dsn)
    yield engine
    await engine.dispose()


async def insert_user(
    engine: AsyncEngine,
    name: str,
    *,
    email: str,
    age: int,
    user_id: uuid.UUID | None = None,
    deleted: bool = False,
) -> uuid.UUID:
    """Insert a 0001-shaped user; `age` 0 is the oldest, each step a day later."""
    user_id = user_id or uuid.uuid4()
    created = BASE_TIME + timedelta(days=age)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO users (id, email, display_name, created_at, deleted_at) "
                "VALUES (:id, :email, :name, :created, :deleted)"
            ),
            {
                "id": user_id,
                "email": email,
                "name": name,
                "created": created,
                "deleted": created if deleted else None,
            },
        )
    return user_id


async def stored(engine: AsyncEngine) -> dict[uuid.UUID, tuple[str, str]]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT id, display_name, display_name_key FROM users")
        )
    return {row[0]: (row[1], row[2]) for row in rows}


async def test_names_are_trimmed_and_normalised(at_0001: AsyncEngine, migration_dsn: str) -> None:
    """Every stored name is tidied with the rules of Req 1, and its key is stored."""
    user = await insert_user(at_0001, f"  {NFD_JOSE} ", email="jose@x.dev", age=0)

    await alembic(migration_dsn, "upgrade", "0002")

    assert (await stored(at_0001))[user] == (NFC_JOSE, "jos" + chr(0xE9))


async def test_duplicates_are_renamed_except_the_oldest(
    at_0001: AsyncEngine, migration_dsn: str
) -> None:
    """The oldest account by `created_at` keeps the name, whatever its id sorts as.

    "Sam" has the highest id and the oldest `created_at`: a build ordering by id
    gives the name to the wrong account. The deleted account's name counts too.
    """
    ids = [
        uuid.UUID("ffffffff-ffff-7fff-8fff-ffffffffffff"),
        uuid.UUID("00000000-0000-7000-8000-000000000001"),
        uuid.UUID("00000000-0000-7000-8000-000000000002"),
        uuid.UUID("00000000-0000-7000-8000-000000000003"),
    ]
    oldest = await insert_user(at_0001, "Sam", email="a@x.dev", age=0, user_id=ids[0])
    middle = await insert_user(at_0001, "sam", email="b@x.dev", age=1, user_id=ids[1])
    newest_deleted = await insert_user(
        at_0001, "SAM", email="c@x.dev", age=2, user_id=ids[2], deleted=True
    )
    alone = await insert_user(at_0001, "Grace", email="d@x.dev", age=3, user_id=ids[3])

    await alembic(migration_dsn, "upgrade", "0002")

    names = {user: name for user, (name, _) in (await stored(at_0001)).items()}
    assert names == {
        oldest: "Sam",
        middle: "sam 2",
        newest_deleted: "SAM 3",
        alone: "Grace",
    }


async def test_duplicates_that_only_normalising_reveals_are_renamed(
    at_0001: AsyncEngine, migration_dsn: str
) -> None:
    """ "José" and " José" (decomposed) are the same name once tidied."""
    first = await insert_user(at_0001, NFC_JOSE, email="a@x.dev", age=0)
    second = await insert_user(at_0001, f" {NFD_JOSE}", email="b@x.dev", age=1)

    await alembic(migration_dsn, "upgrade", "0002")

    names = {user: name for user, (name, _) in (await stored(at_0001)).items()}
    assert names == {first: NFC_JOSE, second: f"{NFC_JOSE} 2"}


async def test_the_index_exists_after_the_upgrade(at_0001: AsyncEngine, migration_dsn: str) -> None:
    """The key is NOT NULL and unique, under the index's own name."""
    await alembic(migration_dsn, "upgrade", "0002")
    insert = text(
        "INSERT INTO users (id, email, display_name, display_name_key) "
        "VALUES (:id, :email, :name, :key)"
    )

    async with at_0001.begin() as connection:
        await connection.execute(
            insert, {"id": uuid.uuid4(), "email": "a@x.dev", "name": "Sam", "key": "sam"}
        )
    with pytest.raises(IntegrityError, match="ux_users_display_name_key"):
        async with at_0001.begin() as connection:
            await connection.execute(
                insert, {"id": uuid.uuid4(), "email": "b@x.dev", "name": "sam", "key": "sam"}
            )
    async with at_0001.begin() as connection:
        await connection.execute(
            insert, {"id": uuid.uuid4(), "email": "c@x.dev", "name": "Sam 2", "key": "sam 2"}
        )
    with pytest.raises(IntegrityError, match="display_name_key"):
        async with at_0001.begin() as connection:
            await connection.execute(
                insert, {"id": uuid.uuid4(), "email": "d@x.dev", "name": "Zed", "key": None}
            )
