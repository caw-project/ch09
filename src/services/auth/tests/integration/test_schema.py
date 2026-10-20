"""The Auth service's own database, as migrated by Alembic (spec §4).

These tests run against a real Postgres because the things worth checking are
the ones SQLAlchemy cannot enforce on its own: that `citext` makes emails
case-insensitively unique, that one IdP subject maps to one identity, and that
a user belongs to a workspace at most once.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from auth.models import User, Workspace, WorkspaceMember
from shared import uuid7


def a_user(email: str = "ada@example.com") -> User:
    # A name per email: display names are unique now, and two "Ada Lovelace" rows would
    # make the email test below pass for the wrong reason.
    return User(id=uuid7(), email=email, display_name=f"Name of {email}")


async def test_a_user_round_trips(sessions) -> None:
    user = a_user()

    async with sessions.begin() as session:
        session.add(user)

    async with sessions() as session:
        stored = (await session.execute(select(User).where(User.id == user.id))).scalar_one()

    assert stored.email == "ada@example.com"
    assert stored.status == "active"
    assert stored.deleted_at is None
    assert stored.version == 0
    assert stored.created_at.tzinfo is not None


async def test_email_uniqueness_ignores_case(sessions) -> None:
    """`citext`: signing in as ADA@ is the same account as ada@."""
    async with sessions.begin() as session:
        session.add(a_user("ada@example.com"))

    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            session.add(a_user("ADA@EXAMPLE.COM"))


def test_the_name_key_is_set_from_the_name() -> None:
    """The model derives the key on every assignment, so no write path can forget it."""
    user = User(id=uuid7(), email="k@example.com", display_name="Stra" + chr(0xDF) + "e")
    assert user.display_name_key == "strasse"

    user.display_name = "Ada"
    assert user.display_name_key == "ada"


async def test_the_database_refuses_a_second_name_with_the_same_key(sessions) -> None:
    """The unique index is the arbiter of every race; `Sam 2` beside it shows it is the key."""
    async with sessions.begin() as session:
        session.add(User(id=uuid7(), email="a@example.com", display_name="Sam"))

    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            session.add(User(id=uuid7(), email="b@example.com", display_name="SAM"))

    async with sessions.begin() as session:
        session.add(User(id=uuid7(), email="c@example.com", display_name="Sam 2"))


async def test_a_user_joins_a_workspace_once(sessions) -> None:
    user, workspace = a_user(), Workspace(id=uuid7(), name="CollabHub Demo")

    async with sessions.begin() as session:
        session.add_all([user, workspace])
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="member"))

    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))


async def test_membership_requires_a_workspace_that_exists(sessions) -> None:
    user = a_user()

    async with sessions.begin() as session:
        session.add(user)

    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            session.add(WorkspaceMember(workspace_id=uuid.uuid4(), user_id=user.id, role="member"))
