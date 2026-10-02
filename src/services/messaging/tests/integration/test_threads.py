"""Threads: replying, the summary on every message, the thread route and the broadcasts (doc 02 §3.1, §3.2).

A reply is a `messages` row with `thread_root_id` set. What only a real Postgres
and a real socket can answer is here: that a reply stays out of history, unread
and `mark_read`; that a root's summary counts non-deleted replies, costs one
grouped query per page and is read *after* the reply commits; and that the
summary and the reply reach the channel room and nobody else.

The rules themselves (normalising a reply id to its root) are unit tested in
`tests/unit/test_threads.py`.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import httpx
import pytest
import socketio
from sqlalchemy import Engine, event, text

WAIT = 5
GROUP_BY = "GROUP BY messages.thread_root_id"


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


async def post_reply(client, headers, channel_id, root_id, body) -> httpx.Response:
    return await client.post(
        f"/api/v1/channels/{channel_id}/messages",
        json={"body": body, "threadRootId": str(root_id)},
        headers=headers,
    )


async def reply(client, headers, channel_id, root_id, body) -> dict:
    response = await post_reply(client, headers, channel_id, root_id, body)
    assert response.status_code == 201, response.text
    return response.json()


async def history(client, headers, channel_id) -> list[dict]:
    response = await client.get(f"/api/v1/channels/{channel_id}/messages", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def in_history(client, headers, channel_id, message_id) -> dict:
    """The one row of history with this id — by id, so a reply leaking into history can't shift it."""
    [row] = [m for m in await history(client, headers, channel_id) if m["id"] == message_id]
    return row


async def thread(client, headers, message_id, **params) -> httpx.Response:
    return await client.get(f"/api/v1/messages/{message_id}/thread", params=params, headers=headers)


async def connected(url: str, token: str) -> socketio.AsyncSimpleClient:
    client = socketio.AsyncSimpleClient()
    await client.connect(
        url, namespace="/messaging", auth={"token": token}, transports=["websocket"]
    )
    return client


async def joined(url: str, token: str, channel_id: str) -> socketio.AsyncSimpleClient:
    client = await connected(url, token)
    assert (await client.call("join_channel", channel_id, timeout=WAIT))["ok"]
    return client


async def two_events(client: socketio.AsyncSimpleClient) -> dict[str, dict]:
    """Two events from the room, by name, in whatever order they arrive."""
    first = await client.receive(timeout=WAIT)
    second = await client.receive(timeout=WAIT)
    return {first[0]: first[1], second[0]: second[1]}


@contextmanager
def recorded_events():
    """`"commit"` and `"summary"` in the order the app's own engine did them.

    Class-level listeners on `Engine`: the app under test has an engine of its
    own, so an instance listener on the `engine` fixture would see nothing (see
    `test_reactions.py`). The summary is the statement that groups by the root.
    """
    events: list[str] = []

    def on_commit(conn):
        events.append("commit")

    def on_execute(conn, cursor, statement, parameters, context, executemany):
        if GROUP_BY in statement:
            events.append("summary")

    event.listen(Engine, "commit", on_commit)
    event.listen(Engine, "before_cursor_execute", on_execute)
    try:
        yield events
    finally:
        event.remove(Engine, "commit", on_commit)
        event.remove(Engine, "before_cursor_execute", on_execute)


async def count_rows(engine, channel_id) -> int:
    async with engine.connect() as connection:
        return await connection.scalar(
            text("SELECT count(*) FROM messages WHERE channel_id = :c"), {"c": channel_id}
        )


# --- sending a reply ---------------------------------------------------------


async def test_a_reply_is_created_under_its_root(client, ada):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")

    answer = await reply(client, ada, channel["id"], root["id"], "I am")

    assert answer["threadRootId"] == root["id"]


async def test_a_reply_to_a_reply_is_filed_under_the_root(client, ada, grace):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")
    first = await reply(client, ada, channel["id"], root["id"], "I am")

    second = await reply(client, grace, channel["id"], first["id"], "me too")

    assert second["threadRootId"] == root["id"]
    assert second["threadRootId"] != first["id"]


async def test_a_deleted_root_still_takes_replies(client, ada):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "oops")
    assert (await client.delete(f"/api/v1/messages/{root['id']}", headers=ada)).status_code == 200

    answer = await reply(client, ada, channel["id"], root["id"], "still here")

    assert answer["threadRootId"] == root["id"]


async def test_an_unknown_root_is_a_404_and_nothing_is_created(client, ada, engine):
    """History never shows a reply, so only the table itself can prove nothing was written."""
    channel = await make_channel(client, ada)
    await send(client, ada, channel["id"], "anchor")
    before = await count_rows(engine, channel["id"])

    response = await post_reply(client, ada, channel["id"], uuid.uuid4(), "into the void")

    assert response.status_code == 404
    assert response.json()["detail"] == "No such thread."
    assert await count_rows(engine, channel["id"]) == before


async def test_a_refused_reply_reaches_no_one(realtime_url, tokens):
    """Grace's first event is the later top-level anchor, so the refused reply was never broadcast."""
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
        grace = await joined(realtime_url, tokens.mint(user_id=tokens.GRACE), channel["id"])

        refused = await post_reply(ada_http, {}, channel["id"], uuid.uuid4(), "into the void")
        await send(ada_http, {}, channel["id"], "anchor")
        _, payload = await grace.receive(timeout=WAIT)

    assert payload["body"] == "anchor"
    assert refused.status_code == 404

    await grace.disconnect()


async def test_a_root_in_another_channel_is_refused(client, ada):
    general = await make_channel(client, ada, "general")
    random = await make_channel(client, ada, "random")
    root = await send(client, ada, random["id"], "over in random")

    response = await post_reply(client, ada, general["id"], root["id"], "wrong room")

    assert response.status_code == 404
    assert response.json()["detail"] == "No such thread."


async def test_a_root_in_a_private_channel_you_cannot_see_answers_as_an_unknown_one(
    client, ada, grace
):
    """CH004: the same status and detail as an id that does not exist, so ids can't be probed."""
    general = await make_channel(client, ada, "general")
    private = await make_channel(client, ada, "leadership", kind="private")
    root = await send(client, ada, private["id"], "the reorg")

    hidden = await post_reply(client, grace, general["id"], root["id"], "let me in")
    unknown = await post_reply(client, grace, general["id"], uuid.uuid4(), "let me in")

    assert hidden.status_code == unknown.status_code == 404
    assert hidden.json()["detail"] == unknown.json()["detail"] == "No such thread."


async def test_a_socket_send_takes_a_thread_root(realtime_url, tokens):
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
        root = await send(ada_http, {}, channel["id"], "who is on call tonight?")
    ada = await connected(realtime_url, tokens.mint())

    ack = await ada.call(
        "send_message",
        {"channelId": channel["id"], "body": "I am", "threadRootId": root["id"]},
        timeout=WAIT,
    )

    assert ack["ok"] is True, ack
    assert ack["data"]["threadRootId"] == root["id"]

    await ada.disconnect()


async def test_a_socket_send_refuses_an_unknown_root(realtime_url, tokens, engine):
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
    ada = await connected(realtime_url, tokens.mint())

    ack = await ada.call(
        "send_message",
        {"channelId": channel["id"], "body": "void", "threadRootId": str(uuid.uuid4())},
        timeout=WAIT,
    )

    assert ack["ok"] is False
    assert ack["problem"]["status"] == 404
    assert ack["problem"]["detail"] == "No such thread."
    assert await count_rows(engine, channel["id"]) == 0

    await ada.disconnect()


# --- out of history, unread and mark_read --------------------------------------


async def test_a_reply_is_not_in_channel_history(client, ada):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")
    await reply(client, ada, channel["id"], root["id"], "I am")

    bodies = [m["body"] for m in await history(client, ada, channel["id"])]

    assert bodies == ["who is on call tonight?"]


async def test_a_reply_is_edited_and_reacted_to_under_its_root(client, ada, grace):
    """R9: the same rules as any message — the author edits, anyone reacts, no one else edits."""
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")
    answer = await reply(client, ada, channel["id"], root["id"], "I am")

    edited = await client.patch(
        f"/api/v1/messages/{answer['id']}",
        json={"body": "I am, until nine", "version": answer["version"]},
        headers=ada,
    )
    reacted = await client.post(
        f"/api/v1/messages/{answer['id']}/reactions", json={"emoji": "tada"}, headers=grace
    )
    refused = await client.patch(
        f"/api/v1/messages/{answer['id']}",
        json={"body": "hijacked", "version": answer["version"] + 1},
        headers=grace,
    )

    assert edited.status_code == 200, edited.text
    assert edited.json()["threadRootId"] == root["id"]
    assert reacted.status_code == 200, reacted.text
    assert reacted.json()["threadRootId"] == root["id"]
    assert refused.status_code == 403


async def test_replies_never_count_as_unread(client, ada, grace):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")
    await reply(client, ada, channel["id"], root["id"], "I am")
    await reply(client, ada, channel["id"], root["id"], "until nine")

    response = await client.get(f"/api/v1/channels/{channel['id']}", headers=grace)

    assert response.json()["unreadCount"] == 1


async def test_marking_a_reply_read_is_a_404_and_the_marker_stays(client, ada, grace):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")
    answer = await reply(client, ada, channel["id"], root["id"], "I am")
    url = f"/api/v1/channels/{channel['id']}/read"
    assert (
        await client.post(url, json={"messageId": root["id"]}, headers=grace)
    ).status_code == 204

    refused = await client.post(url, json={"messageId": answer["id"]}, headers=grace)
    state = await client.get(f"/api/v1/channels/{channel['id']}", headers=grace)

    assert refused.status_code == 404
    assert refused.json()["detail"] == "No such channel."
    assert state.json()["lastReadId"] == root["id"]


async def test_a_socket_mark_read_of_a_reply_acks_a_404(realtime_url, tokens):
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
        root = await send(ada_http, {}, channel["id"], "who is on call tonight?")
        answer = await reply(ada_http, {}, channel["id"], root["id"], "I am")
    grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))

    ack = await grace.call(
        "mark_read", {"channelId": channel["id"], "messageId": answer["id"]}, timeout=WAIT
    )

    assert ack["ok"] is False
    assert ack["problem"]["status"] == 404

    await grace.disconnect()


# --- the summary -----------------------------------------------------------------


async def test_a_root_reports_its_reply_count_and_last_reply_time(client, ada):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")
    await reply(client, ada, channel["id"], root["id"], "I am")
    second = await reply(client, ada, channel["id"], root["id"], "until nine")

    listed = await in_history(client, ada, channel["id"], root["id"])

    assert listed["replyCount"] == 2
    assert listed["lastReplyAt"] == second["createdAt"]


async def test_a_deleted_reply_is_not_counted(client, ada):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")
    older = await reply(client, ada, channel["id"], root["id"], "I am")
    newer = await reply(client, ada, channel["id"], root["id"], "until nine")
    assert older["createdAt"] != newer["createdAt"]
    deleted = await client.delete(f"/api/v1/messages/{newer['id']}", headers=ada)
    assert deleted.status_code == 200

    listed = await in_history(client, ada, channel["id"], root["id"])

    assert listed["replyCount"] == 1
    assert listed["lastReplyAt"] == older["createdAt"]


async def test_a_message_with_no_replies_reports_zero_and_null(client, ada):
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "nobody answered")

    listed = await in_history(client, ada, channel["id"], sent["id"])

    assert listed["replyCount"] == 0
    assert listed["lastReplyAt"] is None
    assert sent["replyCount"] == 0
    assert sent["lastReplyAt"] is None


async def test_a_reply_reports_zero_and_null(client, ada):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")
    answer = await reply(client, ada, channel["id"], root["id"], "I am")
    await reply(client, ada, channel["id"], answer["id"], "and me")

    fetched = await client.get(f"/api/v1/messages/{answer['id']}", headers=ada)

    assert answer["replyCount"] == 0
    assert answer["lastReplyAt"] is None
    assert fetched.json()["replyCount"] == 0
    assert fetched.json()["lastReplyAt"] is None


async def test_a_deleted_root_keeps_its_summary(client, ada):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")
    answer = await reply(client, ada, channel["id"], root["id"], "I am")

    deleted = await client.delete(f"/api/v1/messages/{root['id']}", headers=ada)
    listed = await in_history(client, ada, channel["id"], root["id"])

    assert deleted.json()["replyCount"] == 1
    assert deleted.json()["lastReplyAt"] == answer["createdAt"]
    assert listed["deletedAt"] is not None
    assert listed["replyCount"] == 1


async def test_an_edited_root_keeps_its_summary(realtime_url, tokens):
    """Decision 27: a zero from an edit would overwrite "2 replies" in every window."""
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
        root = await send(ada_http, {}, channel["id"], "who is on call tonight?")
        await reply(ada_http, {}, channel["id"], root["id"], "I am")
        newest = await reply(ada_http, {}, channel["id"], root["id"], "until nine")
        grace = await joined(realtime_url, tokens.mint(user_id=tokens.GRACE), channel["id"])

        response = await ada_http.patch(
            f"/api/v1/messages/{root['id']}",
            json={"body": "who is on call this week?", "version": root["version"]},
        )
        event_name, payload = await grace.receive(timeout=WAIT)

    assert response.json()["replyCount"] == 2
    assert response.json()["lastReplyAt"] == newest["createdAt"]
    assert event_name == "message_edited"
    assert payload["replyCount"] == 2
    assert payload["lastReplyAt"] == newest["createdAt"]

    await grace.disconnect()


async def test_a_reaction_on_a_root_keeps_its_summary(client, ada, grace):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")
    await reply(client, ada, channel["id"], root["id"], "I am")

    response = await client.post(
        f"/api/v1/messages/{root['id']}/reactions", json={"emoji": "eyes"}, headers=grace
    )

    assert response.json()["replyCount"] == 1


async def test_a_socket_edit_and_delete_of_a_root_keep_its_summary(realtime_url, tokens):
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
        root = await send(ada_http, {}, channel["id"], "who is on call tonight?")
        await reply(ada_http, {}, channel["id"], root["id"], "I am")
    ada = await connected(realtime_url, tokens.mint())

    edited = await ada.call(
        "edit_message",
        {"messageId": root["id"], "body": "who is on call?", "version": root["version"]},
        timeout=WAIT,
    )
    deleted = await ada.call("delete_message", {"messageId": root["id"]}, timeout=WAIT)

    assert edited["ok"] is True, edited
    assert edited["data"]["replyCount"] == 1
    assert deleted["ok"] is True, deleted
    assert deleted["data"]["replyCount"] == 1

    await ada.disconnect()


async def test_a_page_of_history_costs_one_summary_query(client, ada):
    """One grouped query for the page, not one per root.

    Counted on `GROUP BY messages.thread_root_id`: the history `SELECT` names
    `thread_root_id` too, so a bare-column filter would count it. A class-level
    listener, for the reason `test_reactions.py` gives.
    """
    channel = await make_channel(client, ada)
    for body in ("one", "two", "three", "four", "five"):
        root = await send(client, ada, channel["id"], body)
        await reply(client, ada, channel["id"], root["id"], f"re: {body}")

    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if GROUP_BY in statement:
            statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        items = await history(client, ada, channel["id"])
    finally:
        event.remove(Engine, "before_cursor_execute", record)

    assert len(statements) == 1, statements
    assert len(items) == 5
    assert all(m["replyCount"] == 1 for m in items)


async def test_a_reply_reads_its_summary_after_it_commits(realtime_url, tokens):
    """Decision 9: read before the commit, two concurrent replies each count only themselves."""
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
        root = await send(ada_http, {}, channel["id"], "who is on call tonight?")

        with recorded_events() as events:
            response = await post_reply(ada_http, {}, channel["id"], root["id"], "I am")

    assert response.status_code == 201, response.text
    assert "summary" in events, events
    assert events.index("summary") > events.index("commit"), events


async def test_a_socket_reply_reads_its_summary_after_it_commits(realtime_url, tokens):
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
        root = await send(ada_http, {}, channel["id"], "who is on call tonight?")
    ada = await connected(realtime_url, tokens.mint())

    with recorded_events() as events:
        ack = await ada.call(
            "send_message",
            {"channelId": channel["id"], "body": "I am", "threadRootId": root["id"]},
            timeout=WAIT,
        )

    assert ack["ok"] is True, ack
    assert "summary" in events, events
    assert events.index("summary") > events.index("commit"), events

    await ada.disconnect()


# --- the thread route --------------------------------------------------------


async def test_the_thread_returns_its_root_and_replies_newest_first(client, ada):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")
    first = await reply(client, ada, channel["id"], root["id"], "I am")
    second = await reply(client, ada, channel["id"], root["id"], "until nine")

    response = await thread(client, ada, root["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["root"]["id"] == root["id"]
    assert body["root"]["replyCount"] == 2
    assert [m["id"] for m in body["items"]] == [second["id"], first["id"]]
    assert body["nextCursor"] is None


async def test_the_thread_pages_by_cursor(client, ada):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")
    ids = [(await reply(client, ada, channel["id"], root["id"], b))["id"] for b in "abc"]

    first = await thread(client, ada, root["id"], limit=2)
    assert first.status_code == 200, first.text
    second = await thread(client, ada, root["id"], limit=2, cursor=first.json()["nextCursor"])

    assert [m["id"] for m in first.json()["items"]] == [ids[2], ids[1]]
    assert first.json()["nextCursor"] is not None
    assert [m["id"] for m in second.json()["items"]] == [ids[0]]
    assert second.json()["nextCursor"] is None
    assert second.json()["root"]["id"] == root["id"]


async def test_the_thread_shows_reply_tombstones(client, ada):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")
    gone = await reply(client, ada, channel["id"], root["id"], "oops wrong thread")
    await reply(client, ada, channel["id"], root["id"], "I am")
    await client.delete(f"/api/v1/messages/{gone['id']}", headers=ada)

    response = await thread(client, ada, root["id"])

    assert response.status_code == 200, response.text
    tombstones = [m for m in response.json()["items"] if m["id"] == gone["id"]]
    assert len(tombstones) == 1
    assert tombstones[0]["deletedAt"] is not None
    assert tombstones[0]["body"] == ""


async def test_a_reply_id_is_not_a_thread(client, ada):
    channel = await make_channel(client, ada)
    root = await send(client, ada, channel["id"], "who is on call tonight?")
    answer = await reply(client, ada, channel["id"], root["id"], "I am")

    response = await thread(client, ada, answer["id"])

    assert response.status_code == 404
    assert response.json()["detail"] == "No such thread."


async def test_a_thread_you_cannot_see_is_a_404(client, ada, grace):
    private = await make_channel(client, ada, "leadership", kind="private")
    root = await send(client, ada, private["id"], "the reorg")
    await reply(client, ada, private["id"], root["id"], "agreed")

    response = await thread(client, grace, root["id"])

    assert response.status_code == 404
    assert response.json()["detail"] == "No such channel."


async def test_an_unknown_thread_is_a_404(client, ada):
    response = await thread(client, ada, uuid.uuid4())

    assert response.status_code == 404
    assert response.json()["detail"] == "No such channel."


# --- the broadcasts ----------------------------------------------------------


async def test_a_reply_and_its_summary_reach_the_room(realtime_url, tokens):
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
        root = await send(ada_http, {}, channel["id"], "who is on call tonight?")
        grace = await joined(realtime_url, tokens.mint(user_id=tokens.GRACE), channel["id"])

        answer = await reply(ada_http, {}, channel["id"], root["id"], "I am")
        received = await two_events(grace)

    assert received["message_received"]["threadRootId"] == root["id"]
    assert received["thread_summary_changed"] == {
        "channelId": channel["id"],
        "rootId": root["id"],
        "replyCount": 1,
        "lastReplyAt": answer["createdAt"],
    }

    await grace.disconnect()


async def test_deleting_a_reply_broadcasts_the_lower_count(realtime_url, tokens):
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
        root = await send(ada_http, {}, channel["id"], "who is on call tonight?")
        answer = await reply(ada_http, {}, channel["id"], root["id"], "I am")
        grace = await joined(realtime_url, tokens.mint(user_id=tokens.GRACE), channel["id"])

        deleted = await ada_http.delete(f"/api/v1/messages/{answer['id']}")
        assert deleted.status_code == 200, deleted.text
        received = await two_events(grace)

    assert received["message_deleted"]["threadRootId"] == root["id"]
    assert received["thread_summary_changed"]["replyCount"] == 0
    assert received["thread_summary_changed"]["lastReplyAt"] is None
    assert received["thread_summary_changed"]["rootId"] == root["id"]

    await grace.disconnect()


async def test_a_socket_reply_broadcasts_the_summary(realtime_url, tokens):
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
        root = await send(ada_http, {}, channel["id"], "who is on call tonight?")
    grace = await joined(realtime_url, tokens.mint(user_id=tokens.GRACE), channel["id"])
    ada = await connected(realtime_url, tokens.mint())

    ack = await ada.call(
        "send_message",
        {"channelId": channel["id"], "body": "I am", "threadRootId": root["id"]},
        timeout=WAIT,
    )
    received = await two_events(grace)

    assert ack["ok"] is True, ack
    assert received["message_received"]["threadRootId"] == root["id"]
    assert received["thread_summary_changed"]["replyCount"] == 1
    assert received["thread_summary_changed"]["rootId"] == root["id"]

    await ada.disconnect()
    await grace.disconnect()


async def test_a_socket_delete_of_a_reply_broadcasts_the_lower_count(realtime_url, tokens):
    """Decision 9: the same rule over `delete_message` as over REST."""
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {}, "general")
        root = await send(ada_http, {}, channel["id"], "who is on call tonight?")
        answer = await reply(ada_http, {}, channel["id"], root["id"], "I am")
    grace = await joined(realtime_url, tokens.mint(user_id=tokens.GRACE), channel["id"])
    ada = await connected(realtime_url, tokens.mint())

    ack = await ada.call("delete_message", {"messageId": answer["id"]}, timeout=WAIT)
    received = await two_events(grace)

    assert ack["ok"] is True, ack
    assert received["thread_summary_changed"]["replyCount"] == 0
    assert received["thread_summary_changed"]["lastReplyAt"] is None

    await ada.disconnect()
    await grace.disconnect()


async def test_a_client_in_another_room_hears_neither(realtime_url, tokens):
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        general = await make_channel(ada_http, {}, "general")
        random = await make_channel(ada_http, {}, "random")
        root = await send(ada_http, {}, general["id"], "who is on call tonight?")
        grace = await joined(realtime_url, tokens.mint(user_id=tokens.GRACE), general["id"])
        elsewhere = await joined(realtime_url, tokens.mint(), random["id"])

        await reply(ada_http, {}, general["id"], root["id"], "I am")
        # The positive half: the right room hears both, so the fan-out has finished.
        received = await two_events(grace)
        assert set(received) == {"message_received", "thread_summary_changed"}

        with pytest.raises(socketio.exceptions.TimeoutError):
            await elsewhere.receive(timeout=2)

    await grace.disconnect()
    await elsewhere.disconnect()
