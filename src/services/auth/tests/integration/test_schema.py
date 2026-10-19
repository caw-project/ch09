"""The Auth service's own database, as migrated by Alembic (spec §4).

These tests run against a real Postgres because the things worth checking are
the ones SQLAlchemy cannot enforce on its own: that `citext` makes emails
case-insensitively unique, that one IdP subject maps to one identity, and that
a user belongs to a workspace at most once.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from auth.models import User, Workspace, WorkspaceMember
from shared import uuid7

E_ACUTE = chr(0xE9)
E_ACUTE_UPPER = chr(0xC9)


def a_user(email: str = "ada@example.com", name: str = "Ada Lovelace") -> User:
    return User(id=uuid7(), email=email, display_name=name)


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

    # A different name, or this would raise for the name and pass for the wrong reason.
    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            session.add(a_user("ADA@EXAMPLE.COM", name="Grace Hopper"))


async def test_the_name_key_is_unique_including_deleted_accounts(sessions) -> None:
    """The index is not partial: a deleted account keeps its name (D46)."""
    gone = a_user("gone@example.com", name="Jos" + E_ACUTE)
    gone.deleted_at = datetime(2026, 9, 1, tzinfo=UTC)
    async with sessions.begin() as session:
        session.add(gone)

    with pytest.raises(IntegrityError) as caught:
        async with sessions.begin() as session:
            session.add(a_user("new@example.com", name="JOS" + E_ACUTE_UPPER))

    assert "ux_users_display_name_key" in str(caught.value)

    # Names that merely share a prefix are different names.
    async with sessions.begin() as session:
        session.add(a_user("ada@example.com", name="Ada"))
        session.add(a_user("adal@example.com", name="Ada L"))


async def test_the_key_is_written_with_the_name_on_insert_and_on_rename(sessions) -> None:
    user = a_user("ada@example.com", name="Ada Lovelace")
    async with sessions.begin() as session:
        session.add(user)

    async with sessions() as session:
        key = await session.scalar(select(User.display_name_key).where(User.id == user.id))
    assert key == "ada lovelace"

    async with sessions.begin() as session:
        stored = (await session.execute(select(User).where(User.id == user.id))).scalar_one()
        stored.display_name = "Grace HOPPER"
    async with sessions() as session:
        key = await session.scalar(select(User.display_name_key).where(User.id == user.id))
    assert key == "grace hopper"


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
