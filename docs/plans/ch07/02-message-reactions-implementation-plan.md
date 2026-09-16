# Message Reactions — TDD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Three project rules override those skills.** **Never commit** — every task ends with the
> worktree dirty; where a skill or a step says "commit", this plan says "leave uncommitted"
> (CLAUDE.md, "Working in this repo"). **Stop at red, twice** — after Task 2 and again after Task 9,
> nothing proceeds until Elton has reviewed the failing tests. **Plans live in `docs/plans/`**, not
> `docs/superpowers/plans/`.

**Goal:** A person can react to a message with one of six emoji, see everyone's counts on every
message, and watch a reaction appear live in another browser — over REST, broadcast on the socket,
aggregated onto the message DTO.

**Architecture:** A new `message_reactions` table whose composite primary key `(message_id,
user_id, emoji)` *is* the concurrency control, so add is `ON CONFLICT DO NOTHING` and remove is a
plain `DELETE`. Two REST routes toggle it and return the full updated message; one grouped query
per page of history aggregates counts onto `MessageResponse.reactions`. A `reaction_changed`
broadcast carries the authoritative count rather than a delta, so applying it is an idempotent set
— safe optimistically, from the response, and from the echo.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async + asyncpg, Alembic, python-socketio,
pydantic v2, pytest + testcontainers, uv, ruff · React 19, TypeScript, TanStack Query, Vitest +
MSW · pytest-bdd + Playwright.

**Spec:** `docs/plans/ch07/01-message-reactions-design.md`. Read it first — this plan argues from
it and does not repeat its reasoning.

**Worktree:** `/Users/elton/scm/manning/caw-reactions`, branch `feature/message-reactions`, from
`main` at `f0ba289`.

---

## Correction to the spec, made while planning

**The `reaction_changed` payload gains `reacted`.** Spec §5 settled on the authoritative `count`
instead of `action: "added" | "removed"`, and that is right — but `count` alone leaves the *actor's*
own client unable to tell which way its toggle went, because an authoritative count carries no
direction. The payload therefore carries the reacting user's resulting state as well:

```
reaction_changed → { messageId, channelId, emoji, count, userId, reacted }
```

`count` is everyone's; `userId` + `reacted` describe one person, and a client applies `reacted`
only when `userId` is its own. Still idempotent, now also determinate. Task 14 writes this back
into the design doc §5 and §6.

## Global Constraints

- The workspace comes from `principal.workspace_id` only — never a path, body or event payload
  (CH001).
- A message the caller cannot see is a **404 with the wording `"No such channel."`**, never a 403
  and never a distinguishable message (CH004).
- `require_user`, never a fail-closed variant: reactions are not in the Conventions §5.2
  fail-closed set.
- **Commit, then publish.** Publishers do nothing when `sio is None`, which is every integration
  test that uses `client`.
- JSON is camelCase, SQL is snake_case. UUID v7 ids compare in time order in Python and Postgres.
- **No foreign key on `user_id`** — it is Auth's row (Conventions §2). `message_id` gets a real one:
  both ends are ours.
- No new environment variable, no chart change, no new runtime dependency.
- The lint hook runs `ruff` and `eslint` after every edit and **blocks** on findings: fix them.
  Convention checks: `python3 .claude/hooks/checks/conventions.py [files...]`.
- Tests are named for the behaviour they protect and carry a one-line docstring saying what breaks
  if the rule goes — the house style in `tests/unit/test_message_policy.py`.

## File map

| File | Change | Responsibility |
|---|---|---|
| `src/services/messaging/messaging/reactions.py` | create | allowlist, validation, `may_react`, `summarise`, add/remove/clear/query |
| `src/services/messaging/messaging/models.py` | modify | `Reaction` model |
| `src/services/messaging/messaging/alembic/versions/0004_reactions.py` | create | `message_reactions` |
| `src/services/messaging/messaging/schemas.py` | modify | `ReactionSummary`, `ReactionRequest`, `MessageResponse.reactions` |
| `src/services/messaging/messaging/routers/messages.py` | modify | `_as_message(row, *, reactions)`, aggregate at the read sites, clear on delete |
| `src/services/messaging/messaging/routers/reactions.py` | create | `POST`/`DELETE` |
| `src/services/messaging/messaging/routers/search.py` | modify | pass summaries into `_as_message` |
| `src/services/messaging/messaging/realtime.py` | modify | `publish_reaction_changed` |
| `src/services/messaging/messaging/realtime_writes.py` | modify | pass `reactions=` at its three `_as_message` calls |
| `src/services/messaging/messaging/main.py` | modify | register the router |
| `src/services/messaging/tests/unit/test_reactions.py` | create | the three pure rules |
| `src/services/messaging/tests/integration/test_reactions.py` | create | routes, SQL, socket |
| `src/services/messaging/tests/integration/test_schema.py` | modify | replace the "not created" assertion |
| `src/services/messaging/tests/integration/conftest.py` | modify | `TABLES` gains `message_reactions` |
| `src/frontend/openapi/messaging.json`, `src/frontend/src/types/messaging.ts` | regenerate | contract |
| `src/frontend/src/lib/api/messaging.ts` | modify | `addReaction`, `removeReaction`, `Reaction` type |
| `src/frontend/src/features/channels/reactions.ts` | create | glyphs + display order |
| `src/frontend/src/features/channels/useMessages.ts` | modify | `setMessageReactions`, `applyReaction`, `useToggleReaction` |
| `src/frontend/src/features/channels/ReactionBar.tsx` | create | chips |
| `src/frontend/src/features/channels/ReactionPicker.tsx` | create | the six-emoji row |
| `src/frontend/src/features/channels/MessageItem.tsx` | modify | render bar + picker |
| `src/frontend/src/features/channels/MessageList.tsx` | modify | hoist the mutation |
| `src/frontend/src/lib/realtime/useChannelSocket.ts` | modify | `reaction_changed` handler |
| `src/frontend/src/test/factories.ts` | modify | `aMessage()` gains `reactions: []` |
| `src/frontend/src/features/channels/*.test.tsx`, `useMessages.test.ts` | create/modify | Vitest |
| `tests/bdd/features/reactions.feature` | create | one journey |
| `tests/bdd/steps/test_reaction_steps.py` | create | its steps |
| `tests/bdd/pages/chat_page.py` | modify | reaction selectors |
| `docs/design/02-messaging-service.md`, `07-open-decisions-register.md`, `docs/adr/` | modify | D39 + ADR |

## How this plan runs

| Phase | Tasks | Ends with |
|---|---|---|
| **RED — backend** | 1–2 | failing pytest unit + integration tests — **STOP for review** |
| GREEN — backend | 3–8 | those pass, nothing else breaks |
| Contract | 9 | OpenAPI + TS regenerated; `tsc` red until the SPA catches up |
| **RED — frontend** | 10 | failing Vitest tests — **STOP for review** |
| GREEN — frontend | 11–13 | those pass |
| Journey | 14 | one BDD scenario, green |
| Finish | 15–16 | register, ADR, docs, full verification |

The frontend cannot be tested before Task 9: `aMessage()` is typed from the generated schema, so
`reactions` does not exist as a field until the OpenAPI document has it. That is why there are two
red checkpoints rather than one.

---

## Task 1: The pure rules (RED)

**Files:**
- Test: `src/services/messaging/tests/unit/test_reactions.py` (create)

**Interfaces:**
- Consumes: nothing yet — this task defines the names Task 4 must implement.
- Produces: the module contract `messaging.reactions` must satisfy —
  `REACTION_EMOJI: tuple[str, ...]`, `UnknownEmojiError(Exception)`,
  `validate(emoji: str) -> str`, `may_react(message: Message) -> bool`,
  `Summary(emoji: str, count: int, reacted: bool)` (frozen dataclass),
  `summarise(rows: Iterable[tuple[uuid.UUID, str, int, bool]]) -> dict[uuid.UUID, list[Summary]]`.

- [ ] **Step 1: Write the failing tests**

```python
"""The reaction rules — the allowlist, the tombstone, and the shape of a summary.

Pure functions over values that are already loaded (register D32), so none of
this needs a session and nothing is faked. That a route *applies* each rule, and
which status it maps to, is proven once in `tests/integration/test_reactions.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from messaging.models import Message
from messaging.reactions import (
    REACTION_EMOJI,
    Summary,
    UnknownEmojiError,
    may_react,
    summarise,
    validate,
)

DELETED_AT = datetime(2026, 9, 16, 10, 0, tzinfo=UTC)
ONE = uuid.uuid4()
TWO = uuid.uuid4()


# --- the allowlist ---------------------------------------------------------


@pytest.mark.parametrize("emoji", REACTION_EMOJI)
def test_every_listed_shortcode_is_accepted(emoji):
    """Breaks if the tuple and the validator ever disagree about what is in the set."""
    assert validate(emoji) == emoji


@pytest.mark.parametrize(
    "emoji",
    [
        pytest.param("shrug", id="not-in-the-set"),
        pytest.param("", id="empty"),
        pytest.param("THUMBSUP", id="uppercase"),
        pytest.param("thumbsup ", id="trailing-space"),
        pytest.param("x" * 33, id="longer-than-the-column"),
        pytest.param("👍", id="the-character-rather-than-the-shortcode"),
    ],
)
def test_anything_else_is_refused(emoji):
    """Breaks if validation is loosened to "any short string" — the column would take it."""
    with pytest.raises(UnknownEmojiError):
        validate(emoji)


def test_the_allowlist_has_no_duplicates_and_fits_the_column():
    """The tuple is the whole rule, so it has to stay well-formed."""
    assert len(set(REACTION_EMOJI)) == len(REACTION_EMOJI)
    assert all(len(emoji) <= 32 for emoji in REACTION_EMOJI)


# --- the tombstone ---------------------------------------------------------


def test_a_live_message_may_be_reacted_to():
    assert may_react(Message(id=ONE, deleted_at=None)) is True


def test_a_deleted_message_may_not_be_reacted_to():
    """Breaks if the state check is dropped — a tombstone would collect reactions."""
    assert may_react(Message(id=ONE, deleted_at=DELETED_AT)) is False


# --- the summary shape -----------------------------------------------------


def test_summaries_are_grouped_by_message():
    rows = [(ONE, "heart", 2, True), (TWO, "heart", 1, False)]

    assert summarise(rows) == {
        ONE: [Summary(emoji="heart", count=2, reacted=True)],
        TWO: [Summary(emoji="heart", count=1, reacted=False)],
    }


def test_summaries_are_ordered_by_the_allowlist_and_not_by_count():
    """Chips must not swap places under the pointer as counts change.

    Breaks if the order is taken from the query, which groups in whatever order
    Postgres finds convenient.
    """
    rows = [(ONE, "check", 1, False), (ONE, "thumbsup", 9, False), (ONE, "heart", 5, False)]

    assert [s.emoji for s in summarise(rows)[ONE]] == ["thumbsup", "heart", "check"]


def test_reacted_is_carried_through_per_emoji():
    """The caller's own state is per emoji, not per message."""
    rows = [(ONE, "thumbsup", 3, True), (ONE, "heart", 1, False)]

    assert summarise(rows)[ONE] == [
        Summary(emoji="thumbsup", count=3, reacted=True),
        Summary(emoji="heart", count=1, reacted=False),
    ]


def test_a_shortcode_no_longer_in_the_allowlist_is_dropped():
    """Widening the set is easy; narrowing it strands rows, and those must not render.

    Breaks if `summarise` trusts whatever the table holds — the sort would then
    raise a KeyError on a retired shortcode instead of ignoring it.
    """
    rows = [(ONE, "retired", 4, True), (ONE, "heart", 1, False)]

    assert summarise(rows)[ONE] == [Summary(emoji="heart", count=1, reacted=False)]


def test_no_rows_is_an_empty_mapping():
    """A message with no reactions gets `[]` from the router, never a missing key."""
    assert summarise([]) == {}
```

- [ ] **Step 2: Run them and watch them fail for the right reason**

Run: `cd /Users/elton/scm/manning/caw-reactions && uv run pytest src/services/messaging/tests/unit/test_reactions.py -v`

Expected: collection error — `ModuleNotFoundError: No module named 'messaging.reactions'`. That is
the correct red: the module does not exist. Do **not** create a stub to make collection succeed.

- [ ] **Step 3: Leave uncommitted**

Nothing is committed in this repo. Move to Task 2.

---

## Task 2: The routes, the SQL and the broadcast (RED)

**Files:**
- Test: `src/services/messaging/tests/integration/test_reactions.py` (create)
- Modify: `src/services/messaging/tests/integration/test_schema.py:26-31`
- Modify: `src/services/messaging/tests/integration/conftest.py:38`

**Interfaces:**
- Consumes: `client`, `ada`, `grace`, `tokens`, `realtime_url`, `engine` from
  `tests/integration/conftest.py`.
- Produces: the HTTP contract Tasks 6–7 must satisfy —
  `POST /api/v1/messages/{message_id}/reactions` with `{"emoji": "..."}` → 200 `MessageResponse`;
  `DELETE /api/v1/messages/{message_id}/reactions/{emoji}` → 200 `MessageResponse`;
  `MessageResponse.reactions` = `[{emoji, count, reacted}]`;
  socket event `reaction_changed` = `{messageId, channelId, emoji, count, userId, reacted}`.

- [ ] **Step 1: Add the new table to the truncate list**

Without this, rows survive between tests and the count assertions fail in ways that look like
application bugs. Child table first — `message_reactions` references `messages`.

```python
#: Child tables first — `message_reactions` references `messages`, and `messages`
#: and `channel_members` both reference `channels`. `CASCADE` would reach them
#: anyway; being explicit is what stops the next person wondering whether the
#: order matters.
TABLES = ("message_reactions", "messages", "channel_reads", "channel_members", "channels")
```

- [ ] **Step 2: Replace the "not created" assertion in `test_schema.py`**

The existing line is `assert "reactions" not in names`. **It is not enough to flip it** — the table
is called `message_reactions`, and `"reactions" not in names` is an exact-match test on a list, so
it would go on passing forever while proving nothing. Replace the line and its comment:

```python
    assert "channels" in names
    assert "channel_members" in names
    assert "messages" in names
    assert "message_reactions" in names
```

Then add, beside the other schema tests:

```python
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


async def test_a_reaction_has_no_soft_delete_and_no_version(engine):
    """Removing a reaction is a real delete, and the key is the concurrency control."""
    rows = await _rows(
        engine,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'message_reactions'",
    )
    names = {r[0] for r in rows}

    assert names == {"message_id", "user_id", "emoji", "created_at"}
```

- [ ] **Step 3: Write the failing integration tests**

```python
"""Reactions: the two routes, the aggregate on the DTO, and the broadcast (doc 02 §3.1.5, §3.2).

The rules themselves are unit tested in `tests/unit/test_reactions.py`. What is
here is everything only a real Postgres and a real socket can answer: that the
composite key makes a repeat add a no-op, that `reacted` is computed per caller,
that a page of history costs one aggregate query rather than one per message,
and that the event carries the count the database actually holds.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import socketio
from sqlalchemy import event

WAIT = 5


async def make_channel(client, headers, name="general", **body) -> dict:
    response = await client.post("/api/v1/channels", json={"name": name, **body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def send(client, headers, channel_id, body) -> dict:
    response = await client.post(
        f"/api/v1/channels/{channel_id}/messages", json={"body": body}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def react(client, headers, message_id, emoji="thumbsup") -> httpx.Response:
    return await client.post(
        f"/api/v1/messages/{message_id}/reactions", json={"emoji": emoji}, headers=headers
    )


async def unreact(client, headers, message_id, emoji="thumbsup") -> httpx.Response:
    return await client.delete(
        f"/api/v1/messages/{message_id}/reactions/{emoji}", headers=headers
    )


async def history(client, headers, channel_id) -> list[dict]:
    response = await client.get(f"/api/v1/channels/{channel_id}/messages", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def connected(url: str, token: str) -> socketio.AsyncSimpleClient:
    client = socketio.AsyncSimpleClient()
    await client.connect(
        url, namespace="/messaging", auth={"token": token}, transports=["websocket"]
    )
    return client


# --- adding and removing ---------------------------------------------------


async def test_a_reaction_comes_back_on_the_message(client, ada):
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "the eagle has landed")

    response = await react(client, ada, sent["id"], "tada")

    assert response.status_code == 200, response.text
    assert response.json()["reactions"] == [{"emoji": "tada", "count": 1, "reacted": True}]


async def test_reacting_twice_leaves_one_reaction(client, ada):
    """The composite primary key is the guarantee — breaks if the insert is not `ON CONFLICT`."""
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "double click")

    assert (await react(client, ada, sent["id"])).status_code == 200
    second = await react(client, ada, sent["id"])

    assert second.status_code == 200
    assert second.json()["reactions"] == [{"emoji": "thumbsup", "count": 1, "reacted": True}]


async def test_removing_a_reaction_takes_the_chip_away(client, ada):
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "never mind")
    await react(client, ada, sent["id"])

    response = await unreact(client, ada, sent["id"])

    assert response.status_code == 200
    assert response.json()["reactions"] == []


async def test_removing_one_that_was_never_there_is_a_no_op(client, ada):
    """Idempotent both ways: a second tab that already removed it must not get an error."""
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "nothing to remove")

    response = await unreact(client, ada, sent["id"])

    assert response.status_code == 200
    assert response.json()["reactions"] == []


async def test_two_people_reacting_with_the_same_emoji_count_as_two(client, ada, grace):
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "standup at four")

    await react(client, ada, sent["id"], "heart")
    response = await react(client, grace, sent["id"], "heart")

    assert response.json()["reactions"] == [{"emoji": "heart", "count": 2, "reacted": True}]


async def test_reacted_is_computed_for_the_caller(client, ada, grace):
    """The per-caller field the whole broadcast design exists to protect.

    Breaks if `reacted` is ever computed once and shared — every reader would
    see the last writer's state.
    """
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "who is in")
    await react(client, ada, sent["id"], "check")

    [for_ada] = await history(client, ada, channel["id"])
    [for_grace] = await history(client, grace, channel["id"])

    assert for_ada["reactions"] == [{"emoji": "check", "count": 1, "reacted": True}]
    assert for_grace["reactions"] == [{"emoji": "check", "count": 1, "reacted": False}]


async def test_reactions_are_ordered_by_the_allowlist(client, ada):
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "all of them")

    for emoji in ("check", "heart", "thumbsup"):
        await react(client, ada, sent["id"], emoji)

    [message] = await history(client, ada, channel["id"])
    assert [r["emoji"] for r in message["reactions"]] == ["thumbsup", "heart", "check"]


# --- what is refused -------------------------------------------------------


async def test_an_unknown_emoji_is_a_400(client, ada):
    """400, not 422: `ProblemException.validation_error` is this platform's answer."""
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "shrug")

    response = await react(client, ada, sent["id"], "shrug")

    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["errors"]["emoji"]


async def test_a_message_in_a_private_channel_you_are_not_in_is_a_404(client, ada, grace):
    """404 and never 403 (CH004) — a 403 would confirm the message is there."""
    channel = await make_channel(client, ada, "launch-plans", kind="private")
    sent = await send(client, ada, channel["id"], "launch is friday")

    response = await react(client, grace, sent["id"])

    assert response.status_code == 404
    assert response.json()["detail"] == "No such channel."


async def test_a_message_in_another_workspace_is_a_404(client, ada, tokens):
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "numbers are in")
    elsewhere = tokens.header(workspace_id=tokens.OTHER_WORKSPACE)

    assert (await react(client, elsewhere, sent["id"])).status_code == 404


async def test_an_unknown_message_is_a_404(client, ada):
    assert (await react(client, ada, uuid.uuid4())).status_code == 404


async def test_reacting_to_a_tombstone_is_a_409(client, ada):
    """Not a 404: the caller can see the tombstone in the history they are reading."""
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "wrong channel, sorry")
    assert (await client.delete(f"/api/v1/messages/{sent['id']}", headers=ada)).status_code == 200

    response = await react(client, ada, sent["id"])

    assert response.status_code == 409
    assert response.json()["detail"] == "This message was deleted."


async def test_deleting_a_message_clears_its_reactions(client, ada, grace):
    """No orphan counts, and a tombstone carries none."""
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "oops")
    await react(client, grace, sent["id"], "eyes")

    deleted = await client.delete(f"/api/v1/messages/{sent['id']}", headers=ada)

    assert deleted.json()["reactions"] == []
    [message] = await history(client, ada, channel["id"])
    assert message["reactions"] == []


# --- the aggregate ---------------------------------------------------------


async def test_a_message_with_no_reactions_reports_an_empty_list(client, ada):
    channel = await make_channel(client, ada)
    await send(client, ada, channel["id"], "nobody cares")

    [message] = await history(client, ada, channel["id"])
    assert message["reactions"] == []


async def test_a_page_of_history_costs_one_reaction_query(client, ada, engine):
    """One grouped query for the page, not one per message.

    This is the whole justification for aggregating onto the DTO rather than
    adding a second endpoint, and an N+1 here is the most likely regression —
    nothing about the response shape would change when it broke.
    """
    channel = await make_channel(client, ada)
    for body in ("one", "two", "three", "four", "five"):
        sent = await send(client, ada, channel["id"], body)
        await react(client, ada, sent["id"], "heart")

    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if "message_reactions" in statement:
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        items = await history(client, ada, channel["id"])
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)

    assert len(items) == 5
    assert all(m["reactions"] == [{"emoji": "heart", "count": 1, "reacted": True}] for m in items)
    assert len(statements) == 1, statements


async def test_a_single_message_read_carries_its_reactions(client, ada):
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "just this one")
    await react(client, ada, sent["id"], "smile")

    response = await client.get(f"/api/v1/messages/{sent['id']}", headers=ada)

    assert response.json()["reactions"] == [{"emoji": "smile", "count": 1, "reacted": True}]


async def test_an_edit_keeps_the_reactions(client, ada):
    """Breaks if the edit route passes `reactions=[]` for convenience."""
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "standup at four")
    await react(client, ada, sent["id"], "tada")

    response = await client.patch(
        f"/api/v1/messages/{sent['id']}",
        json={"body": "standup at five", "version": sent["version"]},
        headers=ada,
    )

    assert response.json()["reactions"] == [{"emoji": "tada", "count": 1, "reacted": True}]


# --- the broadcast ---------------------------------------------------------


async def test_a_reaction_reaches_a_joined_client(realtime_url, tokens):
    """Grace is in the room; the payload carries the count the database holds."""
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
        sent = await send(ada_http, {}, channel["id"], "the eagle has landed")

        grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
        assert (await grace.call("join_channel", channel["id"], timeout=WAIT))["ok"]

        await react(ada_http, {}, sent["id"], "tada")
        event_name, payload = await grace.receive(timeout=WAIT)

    assert event_name == "reaction_changed"
    assert payload == {
        "messageId": sent["id"],
        "channelId": channel["id"],
        "emoji": "tada",
        "count": 1,
        "userId": str(tokens.ADA),
        "reacted": True,
    }

    await grace.disconnect()


async def test_removing_broadcasts_a_zero_count(realtime_url, tokens):
    """Zero is how a chip disappears — breaks if removal publishes nothing."""
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
        sent = await send(ada_http, {}, channel["id"], "never mind")

        grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
        assert (await grace.call("join_channel", channel["id"], timeout=WAIT))["ok"]

        await react(ada_http, {}, sent["id"], "heart")
        assert (await grace.receive(timeout=WAIT))[0] == "reaction_changed"

        await unreact(ada_http, {}, sent["id"], "heart")
        _, payload = await grace.receive(timeout=WAIT)

    assert payload["count"] == 0
    assert payload["reacted"] is False

    await grace.disconnect()


async def test_a_client_in_another_room_hears_nothing(realtime_url, tokens):
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        general = await make_channel(ada_http, {}, "general")
        random = await make_channel(ada_http, {}, "random")
        sent = await send(ada_http, {}, general["id"], "only for general")

        grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
        assert (await grace.call("join_channel", random["id"], timeout=WAIT))["ok"]

        await react(ada_http, {}, sent["id"])

        with pytest.raises(socketio.exceptions.TimeoutError):
            await grace.receive(timeout=2)

    await grace.disconnect()
```

- [ ] **Step 4: Run them and watch them fail for the right reason**

Run: `cd /Users/elton/scm/manning/caw-reactions && scripts/test.sh integration -- src/services/messaging/tests/integration/test_reactions.py`

Expected: every test in the new module fails with 404 or 405 on the unknown route
(`POST /api/v1/messages/{id}/reactions` does not exist), and the `test_schema.py` additions fail
with `relation "message_reactions" does not exist`. The truncate change will also fail the whole
module until the table exists — that is expected and is fixed by Task 3.

- [ ] **Step 5: STOP — the first red checkpoint**

Report to Elton: the test files, the count of failing tests, and the exact failure reasons. **Write
no production code until he has reviewed them.** CLAUDE.md, "Working in this repo".

---

## Task 3: The table and the migration (GREEN)

**Files:**
- Create: `src/services/messaging/messaging/alembic/versions/0004_reactions.py`
- Modify: `src/services/messaging/messaging/models.py` (after `ChannelRead`, before `Message`)

**Interfaces:**
- Consumes: `Base`, `Timestamp` from `models.py`.
- Produces: `messaging.models.Reaction` with columns `message_id`, `user_id`, `emoji`,
  `created_at`.

- [ ] **Step 1: Write the migration**

```python
"""Reactions.

One row per person per emoji per message, and **the composite primary key is the
concurrency control**. Adding is `ON CONFLICT DO NOTHING` and removing is a plain
`DELETE`, so a double-click, a retried request and two tabs racing all converge
on the same state with no version column and nothing to conflict on — the same
argument `0003` makes for the forward-only read marker.

Three columns the conventions would expect are absent on purpose:

* **No `deleted_at`.** Removing a reaction is a real delete: there is no history
  requirement, nothing renders a removed reaction, and a tombstone here would be
  a row nobody may ever read. Conventions §3's soft-delete rule does not apply to
  a table without the column.
* **No `version`.** See the primary key above.
* **No foreign key on `user_id`.** Users are Auth's rows (Conventions §2).
  `message_id` gets a real one — both ends are ours — and it cascades on delete
  so a future hard-delete of a message cannot strand a reaction.

No index beyond the primary key. Every read groups by `message_id`, which leads
the key, so the primary key index serves it.

Revision ID: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMPTZ = TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "message_reactions",
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("emoji", sa.String(32), primary_key=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("message_reactions")
```

- [ ] **Step 2: Write the model**

```python
class Reaction(Base):
    """One person's one emoji on one message.

    Keyed on all three columns, which is what makes adding idempotent — see
    `0004_reactions` for why there is no `version` and no `deleted_at`.
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
```

- [ ] **Step 3: Run the schema tests**

Run: `scripts/test.sh integration -- src/services/messaging/tests/integration/test_schema.py`
Expected: PASS — all five schema assertions, including the three new ones.

- [ ] **Step 4: Leave uncommitted**

---

## Task 4: The reactions domain module (GREEN)

**Files:**
- Create: `src/services/messaging/messaging/reactions.py`

**Interfaces:**
- Consumes: `messaging.models.Reaction`, `messaging.models.Message`.
- Produces: `REACTION_EMOJI`, `UnknownEmojiError`, `validate`, `may_react`, `Summary`,
  `summarise`, and the three session functions
  `add(session, *, message_id, user_id, emoji) -> None`,
  `remove(session, *, message_id, user_id, emoji) -> None`,
  `clear_for_message(session, *, message_id) -> None`,
  `summaries_for(session, *, message_ids, user_id) -> dict[uuid.UUID, list[Summary]]`.

- [ ] **Step 1: Write the module**

```python
"""Reactions (doc 02 §3.1.5, §4).

Same shape as `messages.py`: plain async functions taking an `AsyncSession`
first, pure rules above them, no FastAPI imports.

**The allowlist is the whole validation rule.** Shortcodes rather than emoji
characters, so there is no unicode normalisation, no skin-tone or ZWJ question,
and nothing variable-width in an indexed column — the client decides what glyph
to draw. Widening the tuple later is one line; narrowing it strands rows, which
is why `summarise` ignores a shortcode it no longer knows rather than raising.

**Order comes from the allowlist, not from the query.** Postgres groups in
whatever order suits it, and chips that reorder themselves as counts change move
under the pointer between a person deciding to click and clicking.

This module returns its own `Summary` dataclass rather than the API model: the
domain has no schema imports anywhere in this service, and `routers/messages.py`
is where DTOs get built.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from messaging.models import Message, Reaction

__all__ = [
    "REACTION_EMOJI",
    "Summary",
    "UnknownEmojiError",
    "add",
    "clear_for_message",
    "may_react",
    "remove",
    "summaries_for",
    "summarise",
    "validate",
]

#: What a person may react with. Server-owned and deliberately small: six things
#: a reader recognises at a glance, and no picker that needs a search box.
REACTION_EMOJI: tuple[str, ...] = ("thumbsup", "heart", "tada", "smile", "eyes", "check")

#: Display position, so ordering is a lookup rather than a scan.
_ORDER: dict[str, int] = {emoji: index for index, emoji in enumerate(REACTION_EMOJI)}


class UnknownEmojiError(Exception):
    """Not one of `REACTION_EMOJI`."""


@dataclass(frozen=True)
class Summary:
    """One emoji on one message: how many, and whether the caller is one of them."""

    emoji: str
    count: int
    reacted: bool


def validate(emoji: str) -> str:
    """Return the shortcode unchanged, or raise.

    No trimming and no case folding. A client that sends `"THUMBSUP "` has a bug,
    and quietly accepting it would mean the column holds two spellings of one
    reaction as soon as the normalisation is ever skipped.
    """
    if emoji not in _ORDER:
        raise UnknownEmojiError(emoji)
    return emoji


def may_react(message: Message) -> bool:
    """Whether this message can take a reaction. A tombstone cannot.

    A pure function over the loaded row (register D32), so the rule is unit
    tested with no session; the router maps `False` to a 409.
    """
    return message.deleted_at is None


def summarise(
    rows: Iterable[tuple[uuid.UUID, str, int, bool]],
) -> dict[uuid.UUID, list[Summary]]:
    """Grouped `(message_id, emoji, count, reacted)` rows into per-message summaries.

    Pure, so the ordering rule and the retired-shortcode rule are unit tested
    without a database.
    """
    grouped: dict[uuid.UUID, list[Summary]] = {}
    for message_id, emoji, count, reacted in rows:
        if emoji not in _ORDER:
            continue
        grouped.setdefault(message_id, []).append(
            Summary(emoji=emoji, count=count, reacted=bool(reacted))
        )

    for summaries in grouped.values():
        summaries.sort(key=lambda summary: _ORDER[summary.emoji])
    return grouped


async def summaries_for(
    session: AsyncSession, *, message_ids: Iterable[uuid.UUID], user_id: uuid.UUID
) -> dict[uuid.UUID, list[Summary]]:
    """Every reaction on a page of messages, in **one** grouped query.

    One query for the page and not one per message: that is the entire reason
    reactions are aggregated onto the message DTO rather than served from an
    endpoint of their own, and `test_a_page_of_history_costs_one_reaction_query`
    is what holds it.

    `bool_or` answers "is the caller among them" in the same pass as the count,
    so `reacted` costs no second round trip — and it is computed per request from
    the caller's own id, never cached.
    """
    ids = list(message_ids)
    if not ids:
        return {}

    query = (
        select(
            Reaction.message_id,
            Reaction.emoji,
            func.count().label("count"),
            func.bool_or(Reaction.user_id == user_id).label("reacted"),
        )
        .where(Reaction.message_id.in_(ids))
        .group_by(Reaction.message_id, Reaction.emoji)
    )
    rows = (await session.execute(query)).all()
    return summarise((r.message_id, r.emoji, r.count, r.reacted) for r in rows)


async def add(
    session: AsyncSession, *, message_id: uuid.UUID, user_id: uuid.UUID, emoji: str
) -> None:
    """React, or do nothing if this person already reacted that way.

    `ON CONFLICT DO NOTHING` rather than a read-then-write: two tabs clicking at
    once would both see "not reacted" and one would fail on the key. The
    conflict is the normal case, not an error.
    """
    await session.execute(
        insert(Reaction)
        .values(message_id=message_id, user_id=user_id, emoji=emoji)
        .on_conflict_do_nothing()
    )


async def remove(
    session: AsyncSession, *, message_id: uuid.UUID, user_id: uuid.UUID, emoji: str
) -> None:
    """Take a reaction back. Removing one that is not there is not an error."""
    await session.execute(
        delete(Reaction).where(
            Reaction.message_id == message_id,
            Reaction.user_id == user_id,
            Reaction.emoji == emoji,
        )
    )


async def clear_for_message(session: AsyncSession, *, message_id: uuid.UUID) -> None:
    """Drop every reaction on a message, when it is deleted.

    The foreign key cascades on a *row* delete, and a delete here is a
    tombstone — the row stays. So this is explicit rather than implied.
    """
    await session.execute(delete(Reaction).where(Reaction.message_id == message_id))
```

- [ ] **Step 2: Run the unit tests from Task 1**

Run: `uv run pytest src/services/messaging/tests/unit/test_reactions.py -v`
Expected: PASS, all of them.

- [ ] **Step 3: Run the whole unit layer**

Run: `scripts/test.sh unit`
Expected: PASS — nothing else moved.

- [ ] **Step 4: Leave uncommitted**

---

## Task 5: The DTO (GREEN)

**Files:**
- Modify: `src/services/messaging/messaging/schemas.py:157-192` (`MessageResponse`) and add two
  models

**Interfaces:**
- Consumes: `CamelModel`, `CamelRequest`.
- Produces: `ReactionSummary` (`emoji`, `count`, `reacted`), `ReactionRequest` (`emoji`), and
  `MessageResponse.reactions: list[ReactionSummary]`.

- [ ] **Step 1: Add the two models above `MessageResponse`**

```python
class ReactionSummary(CamelModel):
    """One emoji on a message: how many people, and whether you are one of them.

    **Counts, never user ids.** A "who reacted" list is a second feature with a
    privacy question of its own, and shipping the ids to every client now would
    decide it silently.

    `reacted` is computed for the caller on every request, which is why it can
    never be broadcast: a room gets one payload, and everyone in it would
    receive whoever acted last. The `reaction_changed` event carries the actor's
    id instead, and each client decides for itself.
    """

    emoji: str
    count: int
    reacted: bool


class ReactionRequest(CamelRequest):
    """React with one emoji.

    The shortcode only — the message is in the path and the person is the
    token's `sub`. Validated against the server's allowlist in the domain rather
    than by a Pydantic `Literal`, so an unknown value gets a message under
    `errors.emoji` like every other broken rule, instead of an opaque
    enum error from the wrong layer.
    """

    emoji: str = Field(max_length=32)
```

- [ ] **Step 2: Add the field to `MessageResponse` and correct its docstring**

Replace the "No `reactions`" paragraph (`schemas.py:162-166`) with:

```python
    `reactions` is a summary — one entry per emoji anyone used, with the count
    and whether the caller is one of them — and it is `[]` rather than absent
    when nobody has reacted. Required with no default, like every other field
    here, so the generated TypeScript does not make every render site null-check
    a list the server always sends.
```

and add the field after `attachments`:

```python
    attachments: list[uuid.UUID]
    reactions: list[ReactionSummary]
```

- [ ] **Step 3: Confirm nothing imports a now-wrong shape**

Run: `uv run pytest src/services/messaging/tests/unit -q`
Expected: PASS. The DTO has a new required field but nothing constructs it directly in a unit test.

- [ ] **Step 4: Leave uncommitted**

---

## Task 6: Wiring the aggregate through the read paths (GREEN)

**Files:**
- Modify: `src/services/messaging/messaging/routers/messages.py:82-94` and its five `_as_message`
  call sites
- Modify: `src/services/messaging/messaging/routers/search.py:70`
- Modify: `src/services/messaging/messaging/realtime_writes.py:200,246,276`

**Interfaces:**
- Consumes: `reactions.summaries_for`, `reactions.Summary`.
- Produces: `_as_message(row: Message, *, reactions: list[reactions.Summary]) -> MessageResponse` —
  **keyword-only and required**, so a forgotten call site is a `TypeError` at import-time-adjacent
  test time rather than a message that silently reports no reactions.

- [ ] **Step 1: Change `_as_message`**

```python
def _as_message(row: Message, *, reactions: list[reactions_domain.Summary]) -> MessageResponse:
    """The DTO, with a deleted row's body redacted here rather than in the query.

    Server-side, and `""` rather than `null`: the DTO types `body` as a non-null
    string, so a null would force a check at every render site in the SPA. The
    client renders the tombstone from `deletedAt`.

    **`reactions` is required and keyword-only.** Every caller has to say what
    this message's reactions are, including the ones that say `[]`, because a
    default would make a forgotten aggregate look exactly like a message nobody
    reacted to.
    """
    response = MessageResponse.model_validate(
        row,
        from_attributes=True,
        update={
            "reactions": [
                ReactionSummary(emoji=s.emoji, count=s.count, reacted=s.reacted) for s in reactions
            ]
        },
    )
    return response.model_copy(update={"body": ""}) if row.deleted_at else response
```

Import the domain module under an alias so the parameter name does not shadow it:

```python
from messaging import channels, indexing, messages, realtime
from messaging import reactions as reactions_domain
```

and add `ReactionSummary` to the `messaging.schemas` import list.

> If `model_validate(..., update=...)` is not available in the pinned pydantic, build the DTO with
> `MessageResponse.model_validate(row, from_attributes=True).model_copy(update={"reactions": [...]})`
> instead — same result, one more allocation. Check with
> `uv run python -c "import pydantic; print(pydantic.VERSION)"` before choosing.

- [ ] **Step 2: Add a helper for the two single-message read paths**

```python
async def _one_with_reactions(
    session: AsyncSession, principal: UserPrincipal, row: Message
) -> MessageResponse:
    """A single message's DTO, with its own reactions loaded."""
    found = await reactions_domain.summaries_for(
        session, message_ids=[row.id], user_id=principal.user_id
    )
    return _as_message(row, reactions=found.get(row.id, []))
```

- [ ] **Step 3: Update every call site**

| Site | Change |
|---|---|
| `list_messages` (`:141-144`) | one `summaries_for` over the page, then `_as_message(m, reactions=found.get(m.id, []))` |
| `send_message` (`:180`) | `_as_message(created, reactions=[])` — a new message has none |
| `get_message` (`:194`) | `return await _one_with_reactions(session, principal, await _visible_message(...))` |
| `edit_message` (`:250`) | `await _one_with_reactions(session, principal, edited)` — an edit keeps them |
| `delete_message` (`:293`) | `_as_message(result.message, reactions=[])`, after Task 7 clears them |
| `routers/search.py:70` | one `summaries_for` over the hydrated rows |
| `realtime_writes.py:200,246,276` | `reactions=[]` for send and delete; the socket `edit_message` needs the real ones — call `reactions.summaries_for` there as the REST edit does |

`list_messages` becomes:

```python
    found = await messages.history_page(session, channel_id=channel_id, page=page)
    summaries = await reactions_domain.summaries_for(
        session, message_ids=[m.id for m in found.items], user_id=principal.user_id
    )
    return MessageListResponse(
        items=[_as_message(m, reactions=summaries.get(m.id, [])) for m in found.items],
        next_cursor=found.next_cursor,
    )
```

- [ ] **Step 4: Run the existing message and search suites**

Run: `scripts/test.sh integration -- src/services/messaging/tests/integration/test_messages.py src/services/messaging/tests/integration/test_search.py src/services/messaging/tests/integration/test_realtime_writes.py`
Expected: PASS — every existing test still passes, now with `reactions: []` on every message.

- [ ] **Step 5: Leave uncommitted**

---

## Task 7: The routes and the broadcast (GREEN)

**Files:**
- Create: `src/services/messaging/messaging/routers/reactions.py`
- Modify: `src/services/messaging/messaging/realtime.py` (after `publish_read_receipt`)
- Modify: `src/services/messaging/messaging/main.py:124-130`
- Modify: `src/services/messaging/messaging/routers/messages.py` — `delete_message` clears

**Interfaces:**
- Consumes: `_visible_message`, `_as_message` from `routers/messages.py`; `reactions` domain;
  `realtime.publish_reaction_changed`.
- Produces: the two routes, and
  `publish_reaction_changed(sio, *, channel_id, message_id, emoji, count, user_id, reacted) -> None`.

- [ ] **Step 1: Write the publisher**

```python
async def publish_reaction_changed(
    sio: socketio.AsyncServer | None,
    *,
    channel_id: uuid.UUID,
    message_id: uuid.UUID,
    emoji: str,
    count: int,
    user_id: uuid.UUID,
    reacted: bool,
) -> None:
    """Tell the channel that one emoji's count on one message has changed.

    **The authoritative count, never a delta.** The actor applies its own change
    three times — optimistically, from the REST response, and from its own echo
    of this event — so a `+1` would treble it. A count is an idempotent set,
    safe applied twice or out of order.

    **Not a `MessageResponse`**, which is what `message_deleted` sends. The DTO's
    `reactions[].reacted` is computed for one caller, and a room emit delivers
    one payload to everyone: every recipient would receive the actor's own lit
    state. So the payload names the actor instead — `userId` with the `reacted`
    that now holds for *them* — and each client applies it only to itself.
    """
    if sio is None:
        return

    await sio.emit(
        "reaction_changed",
        {
            "messageId": str(message_id),
            "channelId": str(channel_id),
            "emoji": emoji,
            "count": count,
            "userId": str(user_id),
            "reacted": reacted,
        },
        room=room(channel_id),
        namespace=NAMESPACE,
    )
```

- [ ] **Step 2: Write the router**

```python
"""Reaction endpoints (doc 02 §3.1.5).

Its own module rather than more routes in `routers/messages.py`: a reaction is a
different resource with a different body, and that file is already the longest
in the service.

**Visibility is the guard**, through `_visible_message` — the same 404-before-403
path every message route uses, with the same `"No such channel."` wording so an
id cannot be probed. Anyone who can see the channel may react; there is no
membership gate and no admin gate, because reacting is talking, not
administering.

**Both routes return the whole message.** `PATCH` and `DELETE` on a message
already do, so the SPA writes the response through the one cache helper it
already has instead of growing a second cache keyed by message.

**Both are idempotent**, and that is the composite primary key doing the work,
not a check-then-write. Reacting twice leaves one row; removing a reaction that
was never there is a 200 with the message unchanged.
"""

from __future__ import annotations

import uuid

import socketio
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from messaging import reactions, realtime
from messaging.db import session as db_session
from messaging.routers.messages import _as_message, _visible_message
from messaging.schemas import MessageResponse, ReactionRequest
from shared import ProblemException, UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/messages", tags=["reactions"])


def _validated(emoji: str) -> str:
    try:
        return reactions.validate(emoji)
    except reactions.UnknownEmojiError as exc:
        message = "That is not a reaction you can use."
        raise ProblemException.validation_error(message, errors={"emoji": [message]}) from exc


def _count_of(summaries: list[reactions.Summary], emoji: str) -> tuple[int, bool]:
    """The count and the caller's own state for one emoji, after the write.

    Read off the summaries already built for the response, so the broadcast
    costs no extra query.
    """
    for summary in summaries:
        if summary.emoji == emoji:
            return summary.count, summary.reacted
    return 0, False


async def _respond(
    session: AsyncSession,
    principal: UserPrincipal,
    sio: socketio.AsyncServer | None,
    message,
    emoji: str,
) -> MessageResponse:
    """Build the DTO, commit, then broadcast — the order every write here uses."""
    summaries = (
        await reactions.summaries_for(
            session, message_ids=[message.id], user_id=principal.user_id
        )
    ).get(message.id, [])
    response = _as_message(message, reactions=summaries)
    await session.commit()

    count, reacted = _count_of(summaries, emoji)
    await realtime.publish_reaction_changed(
        sio,
        channel_id=message.channel_id,
        message_id=message.id,
        emoji=emoji,
        count=count,
        user_id=principal.user_id,
        reacted=reacted,
    )
    return response


@router.post("/{message_id}/reactions", response_model=MessageResponse)
async def add_reaction(
    message_id: uuid.UUID,
    body: ReactionRequest,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    sio: socketio.AsyncServer | None = Depends(realtime.server),
) -> MessageResponse:
    """React to a message. Reacting again with the same emoji changes nothing.

    200 rather than 201: the useful answer is the message's new counts, and a
    repeat is not a creation.
    """
    message = await _visible_message(session, principal, message_id)
    emoji = _validated(body.emoji)

    if not reactions.may_react(message):
        # 409 and not 404 — the caller can see this tombstone in the history
        # they are reading, so "no such message" would be a lie about a row on
        # their screen. The same argument `edit_message` makes.
        raise ProblemException.conflict("This message was deleted.")

    await reactions.add(
        session, message_id=message_id, user_id=principal.user_id, emoji=emoji
    )
    return await _respond(session, principal, sio, message, emoji)


@router.delete("/{message_id}/reactions/{emoji}", response_model=MessageResponse)
async def remove_reaction(
    message_id: uuid.UUID,
    emoji: str,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    sio: socketio.AsyncServer | None = Depends(realtime.server),
) -> MessageResponse:
    """Take a reaction back.

    **No tombstone check, unlike the add.** Deleting a message clears its
    reactions, so there is never anything here to remove from one — and a second
    tab that already removed it must not be told the message is in the wrong
    state for a no-op.
    """
    message = await _visible_message(session, principal, message_id)
    emoji = _validated(emoji)

    await reactions.remove(
        session, message_id=message_id, user_id=principal.user_id, emoji=emoji
    )
    return await _respond(session, principal, sio, message, emoji)
```

- [ ] **Step 3: Clear reactions when a message is deleted**

In `routers/messages.py` `delete_message`, after the domain call and before building the response:

```python
    if result.deleted_now:
        # No orphan counts, and a tombstone carries none.
        await reactions_domain.clear_for_message(session, message_id=message_id)

    response = _as_message(result.message, reactions=[])
```

- [ ] **Step 4: Register the router**

In `main.py`, beside the others:

```python
    app.include_router(reactions_router.router)
```

- [ ] **Step 5: Run the new integration tests**

Run: `scripts/test.sh integration -- src/services/messaging/tests/integration/test_reactions.py`
Expected: PASS, every one.

- [ ] **Step 6: Leave uncommitted**

---

## Task 8: The backend is whole (GREEN)

- [ ] **Step 1: Run the whole backend**

Run: `scripts/test.sh`
Expected: lint, unit and integration all green.

- [ ] **Step 2: Run the convention checks**

Run: `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD | grep '\.py$')`
Expected: no findings. Pay attention to CH001 (the workspace claim), CH004 (the 404) and CH009
(`message_reactions` has no `deleted_at`, so no filter is expected).

- [ ] **Step 3: Leave uncommitted**

---

## Task 9: Regenerate the contract

**Files:**
- Regenerate: `src/frontend/openapi/messaging.json`, `src/frontend/src/types/messaging.ts`
- Modify: `src/frontend/src/test/factories.ts:39-53`
- Modify: `src/frontend/src/lib/api/messaging.ts`

- [ ] **Step 1: Regenerate**

```bash
cd /Users/elton/scm/manning/caw-reactions/src/services/messaging
uv run python -m messaging.openapi > ../../frontend/openapi/messaging.json
cd ../../frontend && npm run generate:api
```

- [ ] **Step 2: Add the type export and the two wrappers**

In `src/frontend/src/lib/api/messaging.ts`, beside the other type aliases:

```typescript
export type Reaction = components['schemas']['ReactionSummary']
```

and at the end of the file:

```typescript
/**
 * React to a message, and get the message back with its new counts.
 *
 * Idempotent: reacting again with the same emoji leaves one reaction and still
 * answers 200. The whole message comes back rather than the reactions alone, so
 * the caller writes it through `upsertMessage` like any other change.
 */
export async function addReaction(
  accessToken: string,
  messageId: string,
  emoji: string,
): Promise<Message> {
  const { data, error, response } = await client.POST('/api/v1/messages/{message_id}/reactions', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { message_id: messageId } },
    body: { emoji },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/** Take a reaction back. Removing one that is not there is a 200, not an error. */
export async function removeReaction(
  accessToken: string,
  messageId: string,
  emoji: string,
): Promise<Message> {
  const { data, error, response } = await client.DELETE(
    '/api/v1/messages/{message_id}/reactions/{emoji}',
    {
      headers: { Authorization: `Bearer ${accessToken}` },
      params: { path: { message_id: messageId, emoji } },
    },
  )
  if (error !== undefined) throw problem(response.status, error)
  return data
}
```

- [ ] **Step 3: Add the field to the factory**

```typescript
export function aMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: id(),
    channelId: id(),
    authorId: id(),
    threadRootId: null,
    body: 'hello',
    attachments: [],
    reactions: [],
    createdAt: AT,
    editedAt: null,
    deletedAt: null,
    version: 0,
    ...overrides,
  }
}
```

- [ ] **Step 4: Confirm the contract landed**

Run: `cd src/frontend && npm run typecheck`
Expected: PASS. `reactions` is now a required field the factory supplies, and nothing else
constructs a `Message` by hand.

- [ ] **Step 5: Leave uncommitted**

---

## Task 10: The SPA's failing tests (RED)

**Files:**
- Modify: `src/frontend/src/features/channels/useMessages.test.ts` (add two describes)
- Create: `src/frontend/src/features/channels/ReactionBar.test.tsx`
- Modify: `src/frontend/src/lib/realtime/useChannelSocket.test.tsx` (add one describe)

**Interfaces:**
- Produces: the contract Tasks 11–13 must satisfy —
  `applyReaction(queryClient, key, event: ReactionEvent, myUserId: string): void`,
  `setMessageReactions(queryClient, key, messageId: string, reactions: Reaction[]): void`,
  `useToggleReaction(accessToken, workspaceId, channelId, userId)` taking
  `{ message: Message; emoji: string }`,
  `<ReactionBar reactions={...} onToggle={(emoji) => void} />`,
  `ReactionEvent = { messageId, channelId, emoji, count, userId, reacted }`.

- [ ] **Step 1: Write the cache-writer and mutation tests**

Append to `useMessages.test.ts`, and add the new names to its import from `./useMessages`:

```typescript
describe('applyReaction', () => {
  const MESSAGE = 'message-1'

  function event(overrides: Partial<ReactionEvent> = {}): ReactionEvent {
    return {
      messageId: MESSAGE,
      channelId: CHANNEL,
      emoji: 'tada',
      count: 1,
      userId: 'someone-else',
      reacted: true,
      ...overrides,
    }
  }

  it('sets the count on the message the event names', () => {
    const message = aMessage({ id: MESSAGE })
    const queryClient = seeded(aMessagePage([message]))

    applyReaction(queryClient, key, event({ count: 3 }), ADA)

    expect(itemsIn(queryClient)[0].reactions).toEqual([
      { emoji: 'tada', count: 3, reacted: false },
    ])
  })

  it('is idempotent, because the count is authoritative and not a delta', () => {
    // The actor applies its own change three times: optimistically, from the
    // response, and from its own echo of the broadcast.
    const message = aMessage({ id: MESSAGE })
    const queryClient = seeded(aMessagePage([message]))

    applyReaction(queryClient, key, event({ count: 2 }), ADA)
    applyReaction(queryClient, key, event({ count: 2 }), ADA)
    applyReaction(queryClient, key, event({ count: 2 }), ADA)

    expect(itemsIn(queryClient)[0].reactions).toEqual([
      { emoji: 'tada', count: 2, reacted: false },
    ])
  })

  it('lights the chip only for the person who reacted', () => {
    const message = aMessage({ id: MESSAGE })
    const queryClient = seeded(aMessagePage([message]))

    applyReaction(queryClient, key, event({ userId: ADA, reacted: true }), ADA)

    expect(itemsIn(queryClient)[0].reactions[0].reacted).toBe(true)
  })

  it('leaves my own lit state alone when somebody else reacts', () => {
    const message = aMessage({
      id: MESSAGE,
      reactions: [{ emoji: 'tada', count: 1, reacted: true }],
    })
    const queryClient = seeded(aMessagePage([message]))

    applyReaction(queryClient, key, event({ count: 2, userId: 'grace', reacted: true }), ADA)

    expect(itemsIn(queryClient)[0].reactions).toEqual([
      { emoji: 'tada', count: 2, reacted: true },
    ])
  })

  it('drops the chip when the last reaction goes', () => {
    const message = aMessage({
      id: MESSAGE,
      reactions: [{ emoji: 'tada', count: 1, reacted: true }],
    })
    const queryClient = seeded(aMessagePage([message]))

    applyReaction(queryClient, key, event({ count: 0, userId: ADA, reacted: false }), ADA)

    expect(itemsIn(queryClient)[0].reactions).toEqual([])
  })

  it('keeps chips in allowlist order however they arrive', () => {
    const message = aMessage({
      id: MESSAGE,
      reactions: [{ emoji: 'heart', count: 1, reacted: false }],
    })
    const queryClient = seeded(aMessagePage([message]))

    applyReaction(queryClient, key, event({ emoji: 'check', count: 1 }), ADA)
    applyReaction(queryClient, key, event({ emoji: 'thumbsup', count: 1 }), ADA)

    expect(itemsIn(queryClient)[0].reactions.map((r) => r.emoji)).toEqual([
      'thumbsup',
      'heart',
      'check',
    ])
  })

  it('touches no other message', () => {
    const other = aMessage()
    const queryClient = seeded(aMessagePage([aMessage({ id: MESSAGE }), other]))

    applyReaction(queryClient, key, event(), ADA)

    expect(itemsIn(queryClient)[1]).toEqual(other)
  })

  it('invents no history for a channel nothing has loaded', () => {
    const queryClient = createTestQueryClient()

    applyReaction(queryClient, key, event(), ADA)

    expect(queryClient.getQueryData(key)).toBeUndefined()
  })
})

describe('useToggleReaction', () => {
  const MESSAGE = '0199a000-0000-7000-8000-00000000000a'

  function renderToggle(queryClient: QueryClient) {
    return renderHookWithProviders(
      () => useToggleReaction('token', WORKSPACE, CHANNEL, ADA),
      { queryClient },
    )
  }

  it('lights the chip before the server answers', async () => {
    const message = aMessage({ id: MESSAGE, channelId: CHANNEL })
    const queryClient = seeded(aMessagePage([message]))
    messaging.post('/api/v1/messages/{message_id}/reactions', () => ({
      ...message,
      reactions: [{ emoji: 'tada', count: 1, reacted: true }],
    }))
    const { result } = renderToggle(queryClient)

    act(() => result.current.mutate({ message, emoji: 'tada' }))

    // Before any response: the optimistic write is already in the cache.
    expect(itemsIn(queryClient)[0].reactions).toEqual([
      { emoji: 'tada', count: 1, reacted: true },
    ])
    await vi.waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(itemsIn(queryClient)[0].reactions).toEqual([
      { emoji: 'tada', count: 1, reacted: true },
    ])
  })

  it('removes when the chip is already lit', async () => {
    const message = aMessage({
      id: MESSAGE,
      channelId: CHANNEL,
      reactions: [{ emoji: 'tada', count: 1, reacted: true }],
    })
    const queryClient = seeded(aMessagePage([message]))
    messaging.delete('/api/v1/messages/{message_id}/reactions/{emoji}', () => ({
      ...message,
      reactions: [],
    }))
    const { result } = renderToggle(queryClient)

    act(() => result.current.mutate({ message, emoji: 'tada' }))

    await vi.waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(itemsIn(queryClient)[0].reactions).toEqual([])
    expect(requests().at(-1)?.method).toBe('DELETE')
  })

  it('puts the chip back when the server refuses', async () => {
    const message = aMessage({ id: MESSAGE, channelId: CHANNEL })
    const queryClient = seeded(aMessagePage([message]))
    messaging.problem('post', '/api/v1/messages/{message_id}/reactions', 409, {
      title: 'Conflict',
      detail: 'This message was deleted.',
    })
    const { result } = renderToggle(queryClient)

    act(() => result.current.mutate({ message, emoji: 'tada' }))

    await vi.waitFor(() => expect(result.current.isError).toBe(true))
    expect(itemsIn(queryClient)[0].reactions).toEqual([])
  })
})
```

Add to the imports at the top of that file:

```typescript
import { messaging, requests } from '../../test/api'
import {
  applyReaction,
  useToggleReaction,
  type ReactionEvent,
  // …the existing imports
} from './useMessages'
```

- [ ] **Step 2: Write the component test**

```typescript
/**
 * The chips under a message. Queried by role and text — `data-testid` belongs
 * to the acceptance suite, and a Vitest test neither adds nor reads one.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ReactionBar } from './ReactionBar'

describe('ReactionBar', () => {
  it('renders nothing when nobody has reacted', () => {
    const { container } = render(<ReactionBar reactions={[]} onToggle={() => undefined} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('shows a count per emoji', () => {
    render(
      <ReactionBar
        reactions={[
          { emoji: 'thumbsup', count: 3, reacted: false },
          { emoji: 'heart', count: 1, reacted: true },
        ]}
        onToggle={() => undefined}
      />,
    )

    expect(screen.getByRole('button', { name: /thumbs up/i })).toHaveTextContent('3')
    expect(screen.getByRole('button', { name: /heart/i })).toHaveTextContent('1')
  })

  it('says which reactions are mine, for a screen reader as well as a colour', () => {
    render(
      <ReactionBar
        reactions={[{ emoji: 'heart', count: 1, reacted: true }]}
        onToggle={() => undefined}
      />,
    )

    expect(screen.getByRole('button', { name: /heart/i })).toHaveAttribute('aria-pressed', 'true')
  })

  it('toggles the emoji that was clicked', async () => {
    const onToggle = vi.fn()
    render(
      <ReactionBar
        reactions={[{ emoji: 'heart', count: 1, reacted: true }]}
        onToggle={onToggle}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: /heart/i }))

    expect(onToggle).toHaveBeenCalledWith('heart')
  })
})
```

- [ ] **Step 3: Write the socket test**

Append inside the `describe('useChannelSocket', …)` block:

```typescript
  it('applies a reaction event to the cached message', () => {
    const queryClient = createTestQueryClient()
    const key = messageKeys.list(WORKSPACE, CHANNEL)
    const message = aMessage({ channelId: CHANNEL })
    queryClient.setQueryData<InfiniteData<MessagePage>>(key, {
      pages: [aMessagePage([message])],
      pageParams: [undefined],
    })

    renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL), { queryClient })
    const socket = latestSocket()

    act(() => socket.serverConnect())
    act(() =>
      socket.serverEmit('reaction_changed', {
        messageId: message.id,
        channelId: CHANNEL,
        emoji: 'tada',
        count: 2,
        userId: 'grace',
        reacted: true,
      }),
    )

    expect(historyItems(queryClient, CHANNEL)?.[0].reactions).toEqual([
      { emoji: 'tada', count: 2, reacted: false },
    ])
  })

  it('keeps a reaction that arrives while the history is being refetched', async () => {
    const queryClient = createTestQueryClient()
    const message = aMessage({ channelId: CHANNEL })
    queryClient.setQueryData<InfiniteData<MessagePage>>(messageKeys.list(WORKSPACE, CHANNEL), {
      pages: [aMessagePage([message])],
      pageParams: [undefined],
    })
    const history = holdHistoryFetch(queryClient, CHANNEL)
    renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL), { queryClient })
    const socket = latestSocket()
    act(() => socket.serverConnect())

    act(() =>
      socket.serverEmit('reaction_changed', {
        messageId: message.id,
        channelId: CHANNEL,
        emoji: 'tada',
        count: 1,
        userId: 'grace',
        reacted: true,
      }),
    )
    // The fetch read the channel before the reaction existed.
    await history.answer(aMessagePage([message]))

    expect(historyItems(queryClient, CHANNEL)?.[0].reactions).toEqual([
      { emoji: 'tada', count: 1, reacted: false },
    ])
  })
```

- [ ] **Step 4: Run them and watch them fail for the right reason**

Run: `cd src/frontend && npm test`
Expected: the new tests fail — `applyReaction`, `useToggleReaction` and `ReactionEvent` are not
exported from `./useMessages`, and `./ReactionBar` does not exist. Existing tests still pass.

- [ ] **Step 5: STOP — the second red checkpoint**

Report to Elton and wait for review before writing any SPA code.

---

## Task 11: The cache writers and the mutation (GREEN)

**Files:**
- Create: `src/frontend/src/features/channels/reactions.ts`
- Modify: `src/frontend/src/features/channels/useMessages.ts`

- [ ] **Step 1: The glyphs and the order**

```typescript
/**
 * What the server's shortcodes look like on screen.
 *
 * The server sends `"thumbsup"`, never `"👍"` — so there is no unicode
 * normalisation anywhere in the wire format, and this file is the only place
 * that decides what is drawn. The order is the server's allowlist order, which
 * is also the order chips are displayed in: counts change constantly, and chips
 * that sorted by count would move under the pointer between deciding to click
 * and clicking.
 *
 * Keep in step with `REACTION_EMOJI` in `messaging/reactions.py`. A shortcode
 * missing from here renders as its own name rather than a blank, so a server
 * that widens the set before the SPA does degrades legibly.
 */

export const REACTION_EMOJI = ['thumbsup', 'heart', 'tada', 'smile', 'eyes', 'check'] as const

export const REACTION_GLYPHS: Record<string, string> = {
  thumbsup: '👍',
  heart: '❤️',
  tada: '🎉',
  smile: '😄',
  eyes: '👀',
  check: '✅',
}

/** What a screen reader says, since an emoji alone announces inconsistently. */
export const REACTION_LABELS: Record<string, string> = {
  thumbsup: 'thumbs up',
  heart: 'heart',
  tada: 'celebrate',
  smile: 'smile',
  eyes: 'eyes',
  check: 'check',
}

const ORDER = new Map(REACTION_EMOJI.map((emoji, index) => [emoji as string, index]))

export function glyphFor(emoji: string): string {
  return REACTION_GLYPHS[emoji] ?? emoji
}

export function labelFor(emoji: string): string {
  return REACTION_LABELS[emoji] ?? emoji
}

export function inAllowlistOrder<T extends { emoji: string }>(reactions: T[]): T[] {
  return [...reactions].sort(
    (a, b) => (ORDER.get(a.emoji) ?? Number.MAX_SAFE_INTEGER) - (ORDER.get(b.emoji) ?? Number.MAX_SAFE_INTEGER),
  )
}
```

- [ ] **Step 2: The cache writers**

Append to `useMessages.ts`:

```typescript
/** What `reaction_changed` carries (doc 02 §3.2). */
export interface ReactionEvent {
  messageId: string
  channelId: string
  emoji: string
  /** The authoritative count after the change — never a delta. */
  count: number
  /** Who changed it, so each client can decide its own lit state. */
  userId: string
  /** Whether **that** person now reacts with this emoji. */
  reacted: boolean
}

/** Replace one message's reactions outright. The primitive the two writers share. */
export function setMessageReactions(
  queryClient: QueryClient,
  key: readonly unknown[],
  messageId: string,
  reactions: Reaction[],
): void {
  queryClient.setQueryData<InfiniteMessages>(key, (cached) => {
    if (!cached) return cached
    return {
      ...cached,
      pages: cached.pages.map((page) => ({
        ...page,
        items: page.items.map((m) => (m.id === messageId ? { ...m, reactions } : m)),
      })),
    }
  })
}

/**
 * Apply a reaction event to the cached message.
 *
 * **An idempotent set, not a delta**, which is what makes it safe to run three
 * times for the same change: the actor applies it optimistically, then from the
 * REST response, then from its own echo of the broadcast. `count` is whatever
 * the database holds, so the last one to run is still right.
 *
 * `reacted` in the payload belongs to `userId` and nobody else. Applying it to
 * everyone is the bug that made the event carry facts rather than a
 * `MessageResponse` in the first place: the DTO's `reacted` is computed for one
 * caller, and a room gets one payload.
 *
 * **No-ops when nothing is cached**, like `upsertMessage`, so an event for a
 * channel nobody has opened cannot invent a history.
 */
export function applyReaction(
  queryClient: QueryClient,
  key: readonly unknown[],
  event: ReactionEvent,
  myUserId: string,
): void {
  queryClient.setQueryData<InfiniteMessages>(key, (cached) => {
    if (!cached) return cached
    return {
      ...cached,
      pages: cached.pages.map((page) => ({
        ...page,
        items: page.items.map((m) =>
          m.id === event.messageId ? { ...m, reactions: merged(m.reactions, event, myUserId) } : m,
        ),
      })),
    }
  })
}

function merged(current: Reaction[], event: ReactionEvent, myUserId: string): Reaction[] {
  const others = current.filter((r) => r.emoji !== event.emoji)
  if (event.count === 0) return inAllowlistOrder(others)

  const existing = current.find((r) => r.emoji === event.emoji)
  const reacted = event.userId === myUserId ? event.reacted : (existing?.reacted ?? false)
  return inAllowlistOrder([...others, { emoji: event.emoji, count: event.count, reacted }])
}

/** What the cache should show the moment a chip is clicked, before the server answers. */
function predict(
  message: Message,
  emoji: string,
  channelId: string,
  myUserId: string,
): ReactionEvent {
  const existing = message.reactions.find((r) => r.emoji === emoji)
  const reacted = !(existing?.reacted ?? false)
  return {
    messageId: message.id,
    channelId,
    emoji,
    count: (existing?.count ?? 0) + (reacted ? 1 : -1),
    userId: myUserId,
    reacted,
  }
}

/**
 * Toggle a reaction, lighting the chip before the server has heard about it.
 *
 * **The first optimistic REST mutation in this app**, and deliberate: a toggle
 * that waits for a round trip feels broken, and the writer it needs already
 * exists for the broadcast. The others here are not optimistic because an edit
 * and a delete both change text somebody has to read, and showing the wrong
 * text is worse than showing it half a second late.
 *
 * Rollback is a snapshot restore rather than an inverse event — there is no
 * inverse of "set the count to 3" that is correct when a second change landed
 * in between.
 */
export function useToggleReaction(
  accessToken: string,
  workspaceId: string | null,
  channelId: string,
  userId: string,
) {
  const queryClient = useQueryClient()
  const key = messageKeys.list(workspaceId, channelId)

  return useMutation<
    Message,
    Error,
    { message: Message; emoji: string },
    { messageId: string; previous: Reaction[] }
  >({
    mutationFn: ({ message, emoji }) =>
      message.reactions.some((r) => r.emoji === emoji && r.reacted)
        ? removeReaction(accessToken, message.id, emoji)
        : addReaction(accessToken, message.id, emoji),
    onMutate: ({ message, emoji }) => {
      applyReaction(queryClient, key, predict(message, emoji, channelId, userId), userId)
      return { messageId: message.id, previous: message.reactions }
    },
    onSuccess: (message) => upsertMessage(queryClient, key, message),
    onError: (_error, _variables, context) => {
      if (context) setMessageReactions(queryClient, key, context.messageId, context.previous)
    },
  })
}
```

Extend the imports at the top of the file:

```typescript
import {
  addReaction,
  deleteMessage,
  editMessage,
  listMessages,
  removeReaction,
  type Message,
  type MessagePage,
  type Reaction,
} from '../../lib/api/messaging'
import { inAllowlistOrder } from './reactions'
```

- [ ] **Step 3: Run the tests for this file**

Run: `cd src/frontend && npx vitest run src/features/channels/useMessages.test.ts`
Expected: PASS, the new describes included.

- [ ] **Step 4: Leave uncommitted**

---

## Task 12: The bar, the picker, and the row (GREEN)

**Files:**
- Create: `src/frontend/src/features/channels/ReactionBar.tsx`, `ReactionPicker.tsx`
- Modify: `src/frontend/src/features/channels/MessageItem.tsx`, `MessageList.tsx`

- [ ] **Step 1: `ReactionBar.tsx`**

```typescript
/**
 * The chips under a message: one per emoji anyone used, lit when it is yours.
 *
 * Renders nothing at all when nobody has reacted, so an unreacted message looks
 * exactly as it did before this feature existed.
 *
 * `aria-pressed` rather than colour alone — "mine" is a state, and a chip that
 * only differs by background says nothing to a screen reader.
 */

import type { Reaction } from '../../lib/api/messaging'
import { glyphFor, labelFor } from './reactions'

interface Props {
  reactions: Reaction[]
  onToggle: (emoji: string) => void
}

export function ReactionBar({ reactions, onToggle }: Props) {
  if (reactions.length === 0) return null

  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {reactions.map((reaction) => (
        <button
          key={reaction.emoji}
          type="button"
          data-testid="reaction-chip"
          data-emoji={reaction.emoji}
          data-count={reaction.count}
          aria-pressed={reaction.reacted}
          aria-label={`${labelFor(reaction.emoji)}, ${reaction.count}`}
          onClick={() => onToggle(reaction.emoji)}
          className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${
            reaction.reacted ? 'border-accent bg-accent/10 text-ink' : 'border-edge text-ink-muted'
          }`}
        >
          <span aria-hidden="true">{glyphFor(reaction.emoji)}</span>
          <span>{reaction.count}</span>
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: `ReactionPicker.tsx`**

```typescript
/**
 * The six-emoji row, opened from a message's hover controls.
 *
 * Six things and no search box, so this is a disclosure rather than a popover
 * library: the set is the server's allowlist and it is small enough to show
 * whole. Closing on blur rather than on a document listener keeps it one
 * component with no global state.
 */

import { useState } from 'react'

import { REACTION_EMOJI, glyphFor, labelFor } from './reactions'

interface Props {
  onPick: (emoji: string) => void
}

export function ReactionPicker({ onPick }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <span className="relative">
      <button
        type="button"
        data-testid="reaction-picker"
        aria-expanded={open}
        aria-label="Add a reaction"
        onClick={() => setOpen((was) => !was)}
        className="text-xs text-ink-muted underline"
      >
        React
      </button>

      {open && (
        <span
          className="absolute right-0 z-10 mt-1 flex gap-1 rounded border border-edge bg-surface p-1 shadow"
          onBlur={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node)) setOpen(false)
          }}
        >
          {REACTION_EMOJI.map((emoji) => (
            <button
              key={emoji}
              type="button"
              data-testid="reaction-option"
              data-emoji={emoji}
              aria-label={labelFor(emoji)}
              onClick={() => {
                onPick(emoji)
                setOpen(false)
              }}
              className="rounded px-1 text-base hover:bg-surface-raised"
            >
              <span aria-hidden="true">{glyphFor(emoji)}</span>
            </button>
          ))}
        </span>
      )}
    </span>
  )
}
```

- [ ] **Step 3: Wire them into `MessageItem`**

Add to `Props`: `onToggleReaction: (emoji: string) => void`. Add `canReact`:

```typescript
  const canReact = !deleted && !pending
```

Add the picker inside the existing hover-controls span, before the Edit button:

```typescript
          {canReact && <ReactionPicker onPick={onToggleReaction} />}
```

and the bar after the body branch, still inside the `<article>`:

```typescript
      {!deleted && <ReactionBar reactions={message.reactions} onToggle={onToggleReaction} />}
```

Extend the file docstring:

> A deleted message carries no reactions and offers no picker: the server clears
> them when it tombstones the row, so there is nothing to draw and nothing to add.

- [ ] **Step 4: Hoist the mutation in `MessageList`**

```typescript
  const toggleReaction = useToggleReaction(accessToken, workspaceId, channelId, userId)
```

and on the row:

```typescript
            onToggleReaction={(emoji) => toggleReaction.mutate({ message, emoji })}
```

- [ ] **Step 5: Run the frontend tests**

Run: `cd src/frontend && npm test`
Expected: PASS, including `ReactionBar.test.tsx`. Existing `MessageItem` and `MessageList` tests
still pass — the new prop is required, so update their renders with a `vi.fn()` if `tsc` asks.

- [ ] **Step 6: Leave uncommitted**

---

## Task 13: Live reactions (GREEN)

**Files:**
- Modify: `src/frontend/src/lib/realtime/useChannelSocket.ts`

- [ ] **Step 1: Generalise the in-flight guard**

`reapplyAfterFetch` currently hard-codes `upsertMessage`. Take the action as a callback so both
handlers can use it:

```typescript
function reapplyAfterFetch(queryClient: QueryClient, key: readonly unknown[], apply: () => void) {
  const hash = hashKey(key)
  const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
    if (event.type !== 'updated' || event.query.queryHash !== hash) return
    if (event.query.state.fetchStatus !== 'idle') return

    unsubscribe()
    if (event.query.state.status === 'success') apply()
  })
}
```

and change the existing caller to `reapplyAfterFetch(queryClient, key, () => upsertMessage(queryClient, key, message))`.

- [ ] **Step 2: Add the handler**

`useChannelSocket` needs the signed-in user's id to decide whose lit state an event changes. Add a
`userId: string` parameter and pass it from `ChatLayout`, beside the workspace id.

```typescript
    function onReaction(event: ReactionEvent) {
      const key = messageKeys.list(workspaceId, event.channelId)
      const apply = () => applyReaction(queryClient, key, event, userId)
      apply()
      if (queryClient.isFetching({ queryKey: key, exact: true }) > 0) {
        reapplyAfterFetch(queryClient, key, apply)
      }
    }

    live.on('reaction_changed', onReaction)
```

Extend the file docstring's fourth rule:

> A reaction event carries the authoritative count rather than a delta, so
> applying it twice — here and again when an in-flight fetch lands — is the
> same as applying it once.

- [ ] **Step 3: Run the frontend tests**

Run: `cd src/frontend && npm test`
Expected: PASS, including the two new socket tests.

- [ ] **Step 4: Leave uncommitted**

---

## Task 14: The journey

**Files:**
- Create: `tests/bdd/features/reactions.feature`, `tests/bdd/steps/test_reaction_steps.py`
- Modify: `tests/bdd/pages/chat_page.py`

- [ ] **Step 1: Write the feature**

```gherkin
@bdd
Feature: Reactions

  Sometimes the useful answer to a message is not another message. Anyone who
  can see a channel can react to what was said in it, choosing from a small
  fixed set of emoji, and everyone in the channel sees the same counts.

  A reaction is yours or it is not: reacting twice with the same emoji is still
  one reaction, and clicking a reaction you have already given takes it back.
  Somebody else reacting the same way adds to the count beside yours rather than
  replacing it.

  Reactions arrive while you are looking at the channel, without a reload, the
  same way messages do.

  Background:
    Given Ada is signed in

  Scenario: Grace sees Ada's reaction without reloading
    Given Ada has created a public channel named "general"
    And Ada has sent "the eagle has landed" in "general"
    And Grace is watching the "general" channel
    When Ada reacts to "the eagle has landed" with "tada"
    Then Grace sees "the eagle has landed" with 1 "tada" reaction
    And Ada sees "the eagle has landed" with 1 "tada" reaction
```

- [ ] **Step 2: Add the page object methods**

```python
    # --- reactions --------------------------------------------------------

    def react_to(self, text: str, emoji: str) -> None:
        """Open a message's picker and choose an emoji, waiting for the chip.

        Waiting on the chip rather than on the request covers the cache write
        too: a reaction the server accepted and the SPA never applied would
        leave nothing on screen, and that is worth failing for.
        """
        self._item_for(text).get_by_test_id("reaction-picker").click()
        self.page.locator(f"[data-testid='reaction-option'][data-emoji='{emoji}']").click()
        expect(self._chip(text, emoji)).to_be_visible()

    def has_reaction_count(self, text: str, emoji: str, count: int) -> bool:
        """Whether a message shows `count` of one emoji, waiting for it to get there.

        The count is an attribute rather than the chip's text so the assertion
        does not depend on how the number is rendered beside the glyph.
        """
        self._settle_messages()
        return _holds(
            lambda: expect(self._chip(text, emoji)).to_have_attribute("data-count", str(count))
        )

    def _chip(self, text: str, emoji: str) -> Locator:
        return self._item_for(text).locator(f"[data-testid='reaction-chip'][data-emoji='{emoji}']")
```

- [ ] **Step 3: Write the steps**

```python
"""Step definitions for reactions.feature.

Named `test_*` for the reason the other step modules give: `scenarios()`
generates its test functions into this module, and a module pytest does not
collect is a feature file that silently never runs.

`Given Grace is watching the …` is this feature's own phrasing and stays here.
It is more than "Grace opens the channel": the server puts a connection in a
room only once it has checked the channel is visible, so a reaction sent before
that ack reaches nobody and the scenario would fail for a reason that has
nothing to do with reactions.

The allowlist, the counts, the idempotency and the ordering are proven lower
down (register D32): unit `test_reactions.py` for the rules, Messaging's
integration tests for the routes and the broadcast, and Vitest for the cache.
What is here is the one thing only a browser can show — two people, one count.

No selectors. A step says what a person did; `pages/chat_page.py` knows what to
click.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage

pytestmark = pytest.mark.bdd

scenarios("../features/reactions.feature")


@given(parsers.parse('Grace is watching the "{name}" channel'))
def grace_is_watching(grace: ChatPage, name: str) -> None:
    grace.open()
    grace.open_channel(name)
    grace.wait_for_channel_joined()


@when(parsers.parse('Ada reacts to "{body}" with "{emoji}"'))
def ada_reacts(ada: ChatPage, body: str, emoji: str) -> None:
    ada.react_to(body, emoji)


@then(parsers.parse('Grace sees "{body}" with {count:d} "{emoji}" reaction'))
def grace_sees_reaction(grace: ChatPage, body: str, count: int, emoji: str) -> None:
    assert grace.has_reaction_count(body, emoji, count)


@then(parsers.parse('Ada sees "{body}" with {count:d} "{emoji}" reaction'))
def ada_sees_reaction(ada: ChatPage, body: str, count: int, emoji: str) -> None:
    assert ada.has_reaction_count(body, emoji, count)
```

- [ ] **Step 4: Run the journey**

Run: `scripts/test.sh e2e -- -k reactions`
Expected: PASS. If it fails on the picker not being visible, the message row's hover controls need
a hover first — add `self._item_for(text).hover()` before the click in `react_to`.

- [ ] **Step 5: Leave uncommitted**

---

## Task 15: The decision, the ADR and the docs

**Files:**
- Modify: `docs/design/07-open-decisions-register.md`, `docs/design/02-messaging-service.md`,
  `docs/plans/ch07/01-message-reactions-design.md`
- Create: `docs/adr/260916-message-reactions.md`
- Modify: `src/services/messaging/messaging/schemas.py`, `alembic/versions/0001_channels.py:4-5`,
  `0002_messages.py:25`, `messaging/__init__.py`

- [ ] **Step 1: Add D39 to the register**

In the Messaging table:

| ID | Decision | Options | Status | Notes |
|---|---|---|---|---|
| D39 | How reactions are modelled, written and delivered | (a) fixed shortcode allowlist, REST write, aggregated onto the message DTO · (b) free unicode, socket write, separate endpoint | 🟢 | Settled 2026-09-16. The first entry for a feature the register never covered. Counts without user ids; a "who reacted" list needs its own privacy decision |

- [ ] **Step 2: Write the ADR**

Use the `adr-writer` skill. `docs/adr/260916-message-reactions.md`, covering the three choices that
hold each other up: the composite primary key as the concurrency control, the authoritative count
(plus the actor's `reacted`) in the broadcast rather than a delta or a DTO, and the aggregate on
the message DTO rather than a second endpoint.

- [ ] **Step 3: Update doc 02**

- §3.1: the two routes in the endpoint table.
- §3.1.5: drop the "not built" row; add reaction semantics — the allowlist, idempotency, the
  tombstone 409, removal as a no-op, counts without user ids.
- §3.2: `reaction_changed` with its payload and why it is not a `MessageResponse`.
- §4: `message_reactions`, and why it has no `deleted_at` and no `version`.

- [ ] **Step 4: Update the design doc**

`01-message-reactions-design.md` §5 and §6: the payload carries `reacted` beside `count`. The
"Correction to the spec" section of this plan is the source.

- [ ] **Step 5: Fix the docstrings that say reactions do not exist**

`schemas.py` (done in Task 5), `0001_channels.py:4-5`, `0002_messages.py:25`,
`messaging/__init__.py`.

- [ ] **Step 6: Leave uncommitted**

---

## Task 16: Verification

- [ ] **Step 1: Every layer**

Run: `scripts/test.sh all`
Expected: lint, unit, integration and e2e all green. Note the unit coverage figure and confirm it
has not dropped.

- [ ] **Step 2: Conventions**

Run: `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)`
Expected: no findings.

- [ ] **Step 3: By hand, against a real stack**

```bash
docker compose up -d --build
```

1. React in one browser; watch the count appear in a second without a reload.
2. Click the same chip again — it unlights and the chip disappears at zero.
3. Two people react with the same emoji: the count reads 2 and the chip is lit for both.
4. Double-click a chip fast: the count settles at 1, never 2.
5. React, then delete the message: the chips go with it and the tombstone offers no picker.
6. Stop the socket container; react over REST and confirm the bar still updates from the response.

- [ ] **Step 4: Report, and leave the worktree dirty**

Tell Elton the branch, the worktree path, what changed and what the suites said. **Nothing is
committed.**

---

## Self-review

**Spec coverage.** Every section of `01-message-reactions-design.md` maps to a task: §2 data model →
Tasks 2–3; §3 REST → Tasks 2, 7; §4 DTO and aggregate → Tasks 5–6; §5 broadcast → Tasks 2, 7; §6
SPA → Tasks 9–13; §7 tests → Tasks 1, 2, 10, 14; §8 decisions → Task 15; §9 verification → Task 16.

**Names.** `Summary` (domain) and `ReactionSummary` (DTO) are distinct on purpose and converted in
one place, `_as_message`. `reactions` is the domain module, imported as `reactions_domain` inside
`routers/messages.py` only, where the parameter of the same name would shadow it.
`REACTION_EMOJI` exists twice by design — Python and TypeScript — and Task 11's docstring says to
keep them in step.

**The two gaps this plan knows about.** `useChannelSocket` gains a `userId` parameter in Task 13,
which changes its call site in `ChatLayout` and every existing `useChannelSocket.test.tsx` render;
budget for that. And `test_a_page_of_history_costs_one_reaction_query` hooks SQLAlchemy's
`before_cursor_execute`, which is the only test in the suite that inspects emitted SQL — if it
proves brittle, assert on `len(items)` and the summaries and drop the query count rather than
weakening it to something that cannot fail.
