"""Migration 0002 makes names unique by renaming the duplicates that already exist (gh-3, Req 4).

Each test builds a database at revision 0001, plants accounts the way an
installation that ran without the rule would hold them, and then upgrades it.
The index that forbids duplicates can only be created once there are none, so
the order inside the migration — clean, dedupe, index — is what these pin.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from functools import partial

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from auth.migrations import upgrade
from testkit.databases import service_database

T0 = datetime(2026, 1, 1, tzinfo=UTC)
ZWSP = chr(0x200B)  # zero-width space


@pytest.fixture
def at_0001(postgres_server) -> str:
    """A fresh database migrated to the revision before this feature.

    Synchronous because `service_database` runs the migration with `asyncio.run`.
    """
    return service_database(
        postgres_server, f"auth_mig_{uuid.uuid4().hex[:8]}", partial(upgrade, revision="0001")
    )


async def plant(dsn: str, *accounts: tuple[str, bool]) -> None:
    """Insert accounts oldest first: (display name, deleted)."""
    engine = create_async_engine(dsn)
    try:
        async with engine.begin() as conn:
            for n, (name, deleted) in enumerate(accounts):
                await conn.execute(
                    text(
                        "INSERT INTO users (id, email, display_name, created_at, deleted_at) "
                        "VALUES (:id, :email, :name, :created, :deleted)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "email": f"user{n}@example.com",
                        "name": name,
                        "created": T0 + timedelta(minutes=n),
                        "deleted": T0 if deleted else None,
                    },
                )
    finally:
        await engine.dispose()


async def names(dsn: str) -> list[str]:
    """Display names, oldest account first."""
    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as conn:
            found = await conn.execute(text("SELECT display_name FROM users ORDER BY created_at"))
            return list(found.scalars())
    finally:
        await engine.dispose()


async def test_duplicates_are_renamed_and_the_oldest_keeps_its_name(at_0001: str) -> None:
    """Sam 2 is already held, so the first duplicate skips it — and no one else is touched."""
    await plant(
        at_0001,
        ("Sam", False),
        ("sam", False),
        (" SAM ", False),
        ("Sam 2", False),
        ("Bob", False),
    )

    await upgrade(at_0001, "0002")

    assert await names(at_0001) == ["Sam", "sam 3", "SAM 4", "Sam 2", "Bob"]


async def test_a_deleted_oldest_keeps_its_name(at_0001: str) -> None:
    """Deleted accounts count (D46): the live newer one is the one that moves."""
    await plant(at_0001, ("Ann", True), ("ann", False))

    await upgrade(at_0001, "0002")

    assert await names(at_0001) == ["Ann", "ann 2"]


async def test_stored_names_are_cleaned(at_0001: str) -> None:
    """A stored name that would now fail validation is cleaned so the index can be built."""
    await plant(at_0001, ("Zed" + ZWSP, False), ("   ", False))

    await upgrade(at_0001, "0002")

    assert await names(at_0001) == ["Zed", "user"]


async def test_duplicates_are_found_the_way_the_index_folds_case(at_0001: str) -> None:
    """Postgres `lower()` turns U+0130 into `i`; Python's `str.lower()` into `i` + U+0307.

    The older "İvan" and the newer "ivan" collide in the index, so the newer one
    must move — a comparison made in Python never sees it and the index build fails.
    """
    await plant(at_0001, ("İvan", False), ("ivan", False))

    await upgrade(at_0001, "0002")

    assert await names(at_0001) == ["İvan", "ivan 2"]
    engine = create_async_engine(at_0001)
    try:
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text("INSERT INTO users (id, email, display_name) VALUES (:id, :email, :name)"),
                    {"id": uuid.uuid4(), "email": "late@example.com", "name": "IVAN"},
                )
    finally:
        await engine.dispose()


async def test_afterwards_a_duplicate_cannot_be_inserted(at_0001: str) -> None:
    """The index exists and is case-insensitive — and a different name still goes in."""
    await plant(at_0001, ("Bob", False))
    await upgrade(at_0001, "0002")
    engine = create_async_engine(at_0001)

    async def insert(name: str) -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO users (id, email, display_name) VALUES (:id, :email, :name)"),
                {"id": uuid.uuid4(), "email": f"{uuid.uuid4().hex}@example.com", "name": name},
            )

    try:
        await insert("Bobby")
        with pytest.raises(IntegrityError):
            await insert("BOB")
        async with engine.connect() as conn:
            prefs = await conn.scalar(text("SELECT count(*) FROM user_preferences"))
    finally:
        await engine.dispose()

    assert prefs == 0
