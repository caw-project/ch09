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
from sqlalchemy import Engine, event

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
    return await client.delete(f"/api/v1/messages/{message_id}/reactions/{emoji}", headers=headers)


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
    """400, not 422: `ProblemException.validation_error` is this platform's answer.

    Every other broken field rule on the platform answers the same way — an
    empty message body, a blank search query — and a reaction is not special
    enough to be the one endpoint a client has to handle differently.
    """
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


async def test_a_page_of_history_costs_one_reaction_query(client, ada):
    """One grouped query for the page, not one per message.

    This is the whole justification for aggregating onto the DTO rather than
    adding a second endpoint, and an N+1 here is the most likely regression —
    nothing about the response shape would change when it broke.

    **Listening on `Engine` itself, not on the `engine` fixture.** That fixture
    builds its own engine for truncating tables; the app under test has a
    different one, so an instance listener sees nothing the request does and
    records zero statements — which passes an `== 0` assertion and proves the
    opposite of what it claims. A class-level listener catches every engine in
    the process.
    """
    channel = await make_channel(client, ada)
    for body in ("one", "two", "three", "four", "five"):
        sent = await send(client, ada, channel["id"], body)
        await react(client, ada, sent["id"], "heart")

    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if "message_reactions" in statement:
            statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        items = await history(client, ada, channel["id"])
    finally:
        event.remove(Engine, "before_cursor_execute", record)

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
        "threadRootId": None,
    }

    await grace.disconnect()


async def test_a_reaction_on_a_reply_carries_its_thread_root(realtime_url, tokens):
    """Decision 10: the client routes the event by it. Top-level stays `null` in the test above."""
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
        root = await send(ada_http, {}, channel["id"], "who is on call")
        posted = await ada_http.post(
            f"/api/v1/channels/{channel['id']}/messages",
            json={"body": "I am", "threadRootId": root["id"]},
        )
        assert posted.status_code == 201, posted.text
        answer = posted.json()

        grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
        assert (await grace.call("join_channel", channel["id"], timeout=WAIT))["ok"]

        await react(ada_http, {}, answer["id"], "tada")
        event_name, payload = await grace.receive(timeout=WAIT)

    assert event_name == "reaction_changed"
    assert payload["messageId"] == answer["id"]
    assert payload["threadRootId"] == root["id"]

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

        # socketio raises its own `TimeoutError`, not asyncio's.
        with pytest.raises(socketio.exceptions.TimeoutError):
            await grace.receive(timeout=2)

    await grace.disconnect()
