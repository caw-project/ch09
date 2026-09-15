"""Read state: marking a channel read, the unread count, and the receipt (doc 02 §3.1.7, §3.2).

`POST /channels/{id}/read` and the `mark_read` socket event share
`read_state.mark_read`, so the rules are held once over REST and the fan-out
once over the socket. The unread count is read back from `GET /channels/{id}`,
which is where the sidebar gets it.

The count is a correlated subquery with four conditions, and each one below has
a test that fails without it: no marker, the marker itself, your own messages,
and tombstones.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import socketio

WAIT = 5

#: For a broadcast that must not come. Only ever waited on after a sibling
#: connection has already received the one that should, so the server has
#: finished fanning out by then and a short wait is enough.
QUIET = 1


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


async def mark(client, headers, channel_id, message_id) -> httpx.Response:
    return await client.post(
        f"/api/v1/channels/{channel_id}/read", json={"messageId": str(message_id)}, headers=headers
    )


async def read_state(client, headers, channel_id) -> dict:
    response = await client.get(f"/api/v1/channels/{channel_id}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    return {"lastReadId": body["lastReadId"], "unreadCount": body["unreadCount"]}


async def connected(url: str, token: str) -> socketio.AsyncSimpleClient:
    client = socketio.AsyncSimpleClient()
    await client.connect(
        url, namespace="/messaging", auth={"token": token}, transports=["websocket"]
    )
    return client


async def hears_nothing(client: socketio.AsyncSimpleClient) -> None:
    with pytest.raises(socketio.exceptions.TimeoutError):
        await client.receive(timeout=QUIET)


# --- who may mark what ---------------------------------------------------------


async def test_a_channel_in_another_workspace_is_a_404(client, ada, grace, tokens):
    """Ada's own token for another workspace — and her real marker is untouched.

    The marker row is keyed on channel and user only, so a write that got past
    the workspace check would move Ada's marker in a workspace her token is not
    for.
    """
    channel = await make_channel(client, ada)
    sent = await send(client, grace, channel["id"], "numbers are in")
    elsewhere = tokens.header(workspace_id=tokens.OTHER_WORKSPACE)

    response = await mark(client, elsewhere, channel["id"], sent["id"])

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert await read_state(client, ada, channel["id"]) == {"lastReadId": None, "unreadCount": 1}


async def test_a_private_channel_you_are_not_in_is_a_404(client, ada, grace):
    channel = await make_channel(client, ada, "launch-plans", kind="private")
    sent = await send(client, ada, channel["id"], "launch is friday")

    response = await mark(client, grace, channel["id"], sent["id"])

    assert response.status_code == 404


async def test_a_message_from_another_channel_is_a_404(client, ada, grace):
    """One answer for "not your channel" and "not this channel's message"."""
    general = await make_channel(client, ada, "general")
    random = await make_channel(client, ada, "random")
    elsewhere = await send(client, ada, random["id"], "cat pictures")

    response = await mark(client, grace, general["id"], elsewhere["id"])

    assert response.status_code == 404
    assert (await read_state(client, grace, general["id"]))["lastReadId"] is None


async def test_an_unknown_message_is_a_404(client, ada, grace):
    channel = await make_channel(client, ada)

    response = await mark(client, grace, channel["id"], uuid.uuid4())

    assert response.status_code == 404


# --- the marker ------------------------------------------------------------------


async def test_the_marker_only_moves_forward(client, ada, grace):
    """Two tabs, the slower one arriving last: 204 both times, and no step back."""
    channel = await make_channel(client, ada)
    first, second, _third = [
        await send(client, ada, channel["id"], body) for body in ("one", "two", "three")
    ]

    assert (await mark(client, grace, channel["id"], second["id"])).status_code == 204
    assert (await mark(client, grace, channel["id"], first["id"])).status_code == 204

    assert await read_state(client, grace, channel["id"]) == {
        "lastReadId": second["id"],
        "unreadCount": 1,
    }


# --- the unread count ------------------------------------------------------------


async def test_with_no_marker_every_message_is_unread(client, ada, grace):
    channel = await make_channel(client, ada)
    for body in ("one", "two", "three"):
        await send(client, ada, channel["id"], body)

    assert await read_state(client, grace, channel["id"]) == {"lastReadId": None, "unreadCount": 3}
    # The list reads the same subquery as the detail.
    [listed] = (await client.get("/api/v1/channels", headers=grace)).json()["items"]
    assert listed["unreadCount"] == 3


async def test_your_own_messages_are_never_unread(client, ada, grace):
    channel = await make_channel(client, ada)
    await send(client, ada, channel["id"], "from ada")
    await send(client, ada, channel["id"], "also from ada")
    await send(client, grace, channel["id"], "from grace")

    assert (await read_state(client, grace, channel["id"]))["unreadCount"] == 2
    assert (await read_state(client, ada, channel["id"]))["unreadCount"] == 1


async def test_a_deleted_message_is_not_unread(client, ada, grace):
    """A tombstone is in the history, and is not something to catch up on."""
    channel = await make_channel(client, ada)
    await send(client, ada, channel["id"], "keep this")
    oops = await send(client, ada, channel["id"], "wrong channel")
    assert (await client.delete(f"/api/v1/messages/{oops['id']}", headers=ada)).status_code == 200

    assert (await read_state(client, grace, channel["id"]))["unreadCount"] == 1


async def test_the_marked_message_itself_is_not_unread(client, ada, grace):
    """Read *up to and including* — marking the newest leaves nothing."""
    channel = await make_channel(client, ada)
    await send(client, ada, channel["id"], "one")
    newest = await send(client, ada, channel["id"], "two")

    await mark(client, grace, channel["id"], newest["id"])

    assert (await read_state(client, grace, channel["id"]))["unreadCount"] == 0


# --- the receipt, over the socket ----------------------------------------------


async def test_a_socket_read_tells_the_readers_other_connections_and_nobody_else(
    realtime_url, tokens
):
    """To `user:{workspaceId}:{userId}`, skipping the connection that sent it.

    Grace has joined the channel's room, so a receipt sent to the channel would
    reach her. Ada's connection for another workspace is the same person, so a
    room named without the workspace would reach it.
    """
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {})
        sent = await send(ada_http, {}, channel["id"], "minutes from standup")

    this_tab = await connected(realtime_url, tokens.mint())
    other_tab = await connected(realtime_url, tokens.mint())
    ada_elsewhere = await connected(realtime_url, tokens.mint(workspace_id=tokens.OTHER_WORKSPACE))
    grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
    assert (await grace.call("join_channel", channel["id"], timeout=WAIT))["ok"]

    ack = await this_tab.call(
        "mark_read", {"channelId": channel["id"], "messageId": sent["id"]}, timeout=WAIT
    )
    event, payload = await other_tab.receive(timeout=WAIT)

    assert ack == {"ok": True}
    assert event == "read_receipt_updated"
    assert payload == {
        "channelId": channel["id"],
        "userId": str(tokens.ADA),
        "messageId": sent["id"],
    }
    await hears_nothing(this_tab)
    await hears_nothing(grace)
    await hears_nothing(ada_elsewhere)

    for connection in (this_tab, other_tab, ada_elsewhere, grace):
        await connection.disconnect()


async def test_no_receipt_when_the_marker_did_not_move(realtime_url, tokens):
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as ada_http:
        channel = await make_channel(ada_http, {})
        first = await send(ada_http, {}, channel["id"], "one")
        second = await send(ada_http, {}, channel["id"], "two")

    this_tab = await connected(realtime_url, tokens.mint())
    other_tab = await connected(realtime_url, tokens.mint())
    await this_tab.call(
        "mark_read", {"channelId": channel["id"], "messageId": second["id"]}, timeout=WAIT
    )
    assert (await other_tab.receive(timeout=WAIT))[0] == "read_receipt_updated"

    ack = await this_tab.call(
        "mark_read", {"channelId": channel["id"], "messageId": first["id"]}, timeout=WAIT
    )

    assert ack == {"ok": True}
    await hears_nothing(other_tab)

    await this_tab.disconnect()
    await other_tab.disconnect()
