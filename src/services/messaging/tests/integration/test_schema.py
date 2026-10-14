"""The migration produces the schema the models and the design doc describe.

Cheap to write and it catches the failure mode that hurts most: a model edited
without its migration, which passes every test that goes through SQLAlchemy and
then fails on a real deployment.
"""

from __future__ import annotations

from sqlalchemy import text


async def _rows(engine, sql: str, **params) -> list[tuple]:
    async with engine.connect() as connection:
        result = await connection.execute(text(sql), params)
        return list(result.all())


async def test_the_expected_tables_exist(engine):
    rows = await _rows(
        engine,
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename",
    )
    names = [r[0] for r in rows]

    assert "channels" in names
    assert "channel_members" in names
    assert "messages" in names
    assert "message_reactions" in names


async def test_timestamps_are_timestamptz(engine):
    rows = await _rows(
        engine,
        """
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_name = 'channels'
          AND column_name IN ('created_at', 'updated_at', 'archived_at')
        """,
    )

    assert dict(rows) == {
        "created_at": "timestamp with time zone",
        "updated_at": "timestamp with time zone",
        "archived_at": "timestamp with time zone",
    }


async def test_channels_soft_delete_with_archived_at_not_deleted_at(engine):
    rows = await _rows(
        engine,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'channels'",
    )
    names = {r[0] for r in rows}

    assert "archived_at" in names
    assert "deleted_at" not in names


async def test_the_public_name_index_is_partial_and_case_folded(engine):
    rows = await _rows(
        engine,
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'ux_channels_public_name'",
    )

    assert len(rows) == 1
    # Postgres re-renders the expression with its casts — `lower((name)::text)`
    # rather than `lower(name)` — so match the parts, not the spelling.
    definition = rows[0][0]
    assert "UNIQUE" in definition
    assert "lower(" in definition
    assert "WHERE" in definition
    assert "'public'" in definition


async def test_the_dm_pair_index_is_unique_and_partial_on_kind_dm(engine):
    """One DM per pair per workspace is this index (get-or-create's ON CONFLICT names it).

    Breaks if it is not unique, drops `workspace_id` (one DM per pair across workspaces), or is
    not partial (public channels would be held to it as well).
    """
    rows = await _rows(
        engine, "SELECT indexdef FROM pg_indexes WHERE indexname = 'ux_channels_dm_pair'"
    )

    assert len(rows) == 1, "no index named ux_channels_dm_pair"
    definition = rows[0][0]
    assert "UNIQUE" in definition
    assert "(workspace_id, name)" in definition
    # `kind` is a varchar, so Postgres prints `((kind)::text = 'dm'::text)`: match the parts.
    assert "WHERE" in definition
    assert "'dm'" in definition


async def test_the_indexes_the_sidebar_needs_exist(engine):
    rows = await _rows(
        engine,
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'",
    )
    names = {r[0] for r in rows}

    assert "ix_channel_members_user" in names
    assert "ix_channels_workspace_name" in names


async def test_cross_service_ids_carry_no_foreign_keys(engine):
    """`workspace_id` and `created_by` name rows in another service's database."""
    rows = await _rows(
        engine,
        """
        SELECT conname, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE contype = 'f' AND conrelid::regclass::text IN ('channels', 'channel_members')
        """,
    )
    definitions = " ".join(d for _, d in rows)

    assert "workspace_id" not in definitions
    assert "created_by" not in definitions
    assert "user_id" not in definitions
    # The one foreign key that is allowed: both ends are ours.
    assert "REFERENCES channels(id)" in definitions


async def test_message_timestamps_are_timestamptz(engine):
    rows = await _rows(
        engine,
        """
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_name = 'messages'
          AND column_name IN ('created_at', 'edited_at', 'deleted_at')
        """,
    )

    assert dict(rows) == {
        "created_at": "timestamp with time zone",
        "edited_at": "timestamp with time zone",
        "deleted_at": "timestamp with time zone",
    }


async def test_the_history_index_is_not_partial(engine):
    """The read path returns tombstones, so it has no `deleted_at` clause.

    A partial index with `WHERE deleted_at IS NULL` would silently not be used
    by the query it was created for — the failure mode is a full scan on a busy
    channel, which no test that only checks results would ever catch.
    """
    rows = await _rows(
        engine,
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_messages_channel_time'",
    )

    assert len(rows) == 1
    definition = rows[0][0]
    assert "channel_id" in definition
    assert "DESC" in definition
    assert "WHERE" not in definition


async def test_the_thread_index_is_partial_on_thread_root_id(engine):
    """Top-level rows never enter it; breaks if it is plain, or leads with another column."""
    rows = await _rows(
        engine,
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_messages_thread'",
    )

    assert len(rows) == 1
    definition = rows[0][0]
    assert "(thread_root_id, id)" in definition
    assert "WHERE (thread_root_id IS NOT NULL)" in definition


async def test_a_message_references_its_channel_but_not_its_author(engine):
    """The Conventions §2 service boundary, drawn in DDL.

    A channel is this service's row and gets a real foreign key. An author is a
    row in Auth's database and gets none.
    """
    rows = await _rows(
        engine,
        """
        SELECT pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE contype = 'f' AND conrelid::regclass::text = 'messages'
        """,
    )
    definitions = " ".join(d for (d,) in rows)

    assert "REFERENCES channels(id)" in definitions
    assert "author_id" not in definitions


async def test_a_reaction_references_its_message_but_not_its_user(engine):
    """The Conventions §2 boundary again: a message is ours, a user is Auth's."""
    rows = await _rows(
        engine,
        """
        SELECT pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE contype = 'f' AND conrelid::regclass::text = 'message_reactions'
        """,
    )
    definitions = " ".join(d for (d,) in rows)

    assert "REFERENCES messages(id)" in definitions
    assert "user_id" not in definitions


async def test_the_reaction_key_is_message_user_and_emoji(engine):
    """The primary key *is* the idempotency guarantee — a narrower one would allow duplicates."""
    rows = await _rows(
        engine,
        """
        SELECT pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE contype = 'p' AND conrelid::regclass::text = 'message_reactions'
        """,
    )

    assert len(rows) == 1
    assert rows[0][0] == "PRIMARY KEY (message_id, user_id, emoji)"


async def test_message_attachments_key_and_uniqueness(engine):
    """Decisions 5 and 8: keyed by message and position, one message per asset, no FK to Asset.

    The unique `asset_id` is the second guard behind the claim, and a duplicate
    id in one send. The only foreign key is to `messages`: an asset is Asset's
    row (Conventions §2).
    """
    columns = await _rows(
        engine,
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_name = 'message_attachments'",
    )
    keys = await _rows(
        engine,
        """
        SELECT contype::text, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid::regclass::text = 'message_attachments'
        """,
    )
    # Postgres quotes `position` (a keyword) when it prints a definition.
    definitions = {(kind, definition.replace('"', "")) for kind, definition in keys}
    foreign = " ".join(d for kind, d in keys if kind == "f")

    assert {c[0] for c in columns} == {
        "message_id",
        "position",
        "asset_id",
        "file_name",
        "content_type",
        "size_bytes",
    }
    assert ("p", "PRIMARY KEY (message_id, position)") in definitions
    assert ("u", "UNIQUE (asset_id)") in definitions
    assert "REFERENCES messages(id)" in foreign
    assert "asset_id" not in foreign


async def test_messages_has_no_attachments_column(engine):
    """Decided 5: the never-used `uuid[]` is dropped in the same migration."""
    rows = await _rows(
        engine,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'messages'",
    )
    names = {r[0] for r in rows}

    assert "body" in names
    assert "attachments" not in names


async def test_a_reaction_has_no_soft_delete_and_no_version(engine):
    """Removing a reaction is a real delete, and the key is the concurrency control."""
    rows = await _rows(
        engine,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'message_reactions'",
    )
    names = {r[0] for r in rows}

    assert names == {"message_id", "user_id", "emoji", "created_at"}
