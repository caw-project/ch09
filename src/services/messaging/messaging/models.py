"""SQLAlchemy models for the Messaging service's own database (spec §4).

Only Messaging reads these tables; every other service learns about channels
through this service's API or an event (Conventions §2).

Two things differ from the DDL in docs/design/02-messaging-service.md §4, both
decided while planning slice 1 and reflected back into that doc:

* `ux_channels_public_name` folds case. `#General` and `#general` being two
  different channels is a support ticket, and people say channel names out loud
  where case does not exist. The name is stored exactly as typed — only the
  index is folded.
* Two indexes the spec omits. `channel_members` had only its composite primary
  key, which answers "who is in this channel?" but not "which channels is this
  user in?" — the query the sidebar runs on every page load.

Note also what is *not* here: `channels` has no `deleted_at`. Its soft-delete
column is `archived_at` (spec §4, and `DELETE /channels/{id}` is an archive), so
"filter `deleted_at IS NULL`" from Conventions §3 reads as `archived_at IS NULL`
for this table. `workspace_id`, `created_by` and `channel_members.user_id` carry
no foreign keys, because they name rows in other services' databases.

`messages` is the mirror image and the other documented exception to the same
Conventions §3 rule. It *does* have `deleted_at` — and the read path deliberately
does **not** filter it. A deleted message stays in history as a tombstone with
its body redacted server-side, because a tombstone a reload erases is not a
tombstone. That is why `ix_messages_channel_time` carries no
`WHERE deleted_at IS NULL` predicate: the query that would use it does not have
that clause. The rule is "filter the soft-delete column *unless the doc says
otherwise*", and this is one of the two places it says otherwise.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Every timestamp on the platform is UTC `timestamptz` (Conventions §3).
Timestamp = TIMESTAMP(timezone=True)

PUBLIC = "public"
PRIVATE = "private"
DM = "dm"

#: Kinds a client may create by name. A `dm` is opened through
#: `POST /channels/dm` instead (register D8b), which keys it on the pair of
#: people; there is no creator-as-admin.
CREATABLE_KINDS = (PUBLIC, PRIVATE)

ADMIN = "admin"
MEMBER = "member"


class Base(DeclarativeBase):
    pass


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (
        # A partial *index*, not a table constraint: PostgreSQL has no
        # `UNIQUE (...) WHERE ...` on a constraint. Names are unique among
        # public channels; private channels may repeat one, and a DM's name is
        # its pair key, made unique by `ux_channels_dm_pair`.
        Index(
            "ux_channels_public_name",
            "workspace_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("kind = 'public'"),
        ),
        # One DM per pair of people: `name` holds the pair key (`messaging.dms`).
        # Get-or-create's `ON CONFLICT` names this index.
        Index(
            "ux_channels_dm_pair",
            "workspace_id",
            "name",
            unique=True,
            postgresql_where=text("kind = 'dm'"),
        ),
        # Covers the sidebar query: one workspace, unarchived, name-ordered.
        Index(
            "ix_channels_workspace_name",
            "workspace_id",
            "name",
            "id",
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    topic: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String, nullable=False, server_default=PUBLIC)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class ChannelMember(Base):
    """Who is in a channel, and what they may do to it.

    Channel membership is *not* workspace membership (spec §3.1): these roles
    are `admin`/`member` within one channel and have nothing to do with the
    workspace roles in the token's `roles` claim.
    """

    __tablename__ = "channel_members"
    __table_args__ = (
        # "Which channels is this user in?" — the primary key leads with
        # channel_id and cannot answer it.
        Index("ix_channel_members_user", "user_id", "channel_id"),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(String, nullable=False, server_default=MEMBER)
    joined_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )


class ChannelRead(Base):
    """How far one person has read in one channel.

    Keyed on the channel and the person, not on membership: anyone who can see
    a channel can read it, so anyone who can see it has a place they read up
    to. See `0003_channel_reads` for why there is no `version` and no foreign key
    on `last_read_id`.
    """

    __tablename__ = "channel_reads"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    last_read_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )


class Message(Base):
    """Something somebody said in a channel (spec §4).

    `thread_root_id` makes a row a reply (single-level threads, register D8a).
    `version` is the optimistic-concurrency guard for edits and the external
    version an Elasticsearch index uses (register D25).

    A message's attachments are not a column: they are `MessageAttachment` rows,
    read page-wide the way reactions are (`0006_message_attachments`).

    `channel_id` carries a foreign key and `author_id` does not, and that is the
    Conventions §2 boundary drawn in DDL: a channel is this service's row, and a
    user is Auth's.
    """

    __tablename__ = "messages"
    __table_args__ = (
        # The history read: one channel, newest first. **No
        # `WHERE deleted_at IS NULL`** — history returns tombstones, so the read
        # path has no such clause and would not match a partial index.
        #
        Index("ix_messages_channel_time", "channel_id", text("id DESC")),
        # Threads (`0005_thread_index`). Partial: top-level rows, almost all of
        # the table, never enter it. `(thread_root_id, id)` serves the per-page
        # reply summary and the replies page's keyset alike.
        Index(
            "ix_messages_thread",
            "thread_root_id",
            "id",
            postgresql_where=text("thread_root_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    thread_root_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )
    edited_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class MessageAttachment(Base):
    """A file on a message: a snapshot of what Asset said when it was claimed.

    Keyed on the message and the attach order. `asset_id` is `UNIQUE` — a second
    guard behind Asset's claim — and carries no foreign key, because the asset is
    Asset's row (Conventions §2). `message_id` does, and it cascades. See
    `0006_message_attachments`.
    """

    __tablename__ = "message_attachments"
    __table_args__ = (UniqueConstraint("asset_id"),)

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)


class Reaction(Base):
    """One person's one emoji on one message.

    Keyed on all three columns, and that key *is* the idempotency guarantee:
    adding is an `ON CONFLICT DO NOTHING` insert, so a double-click cannot
    double-count and two tabs cannot collide. See `0004_reactions` for why there
    is no `version` and no `deleted_at`.

    `message_id` carries a foreign key and `user_id` does not — the Conventions
    §2 boundary, the same way `Message` draws it.
    """

    __tablename__ = "message_reactions"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    emoji: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )
