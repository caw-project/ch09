"""`channel_added` and the socket's view of a DM (issue 5, R8, R10, R11).

When a DM gets its first top-level message, both members' personal rooms
(`user:{workspace}:{user}`) hear `channel_added {channelId}` on every send path,
and nobody else does. The sidebar refetches on it; the event carries only the id.

Against the same uvicorn-on-an-ephemeral-port fixture as the other socket tests.
Every test reaches `open_dm` first, so before the route exists each fails there,
at `assert 405 == 200`.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
import socketio

WAIT = 5

#: For a broadcast that must not come. Only ever waited on after something else has
#: been received, so the server has finished fanning out by then.
QUIET = 1

ALAN = uuid.uuid4()


async def connected(url: str, token: str) -> socketio.AsyncSimpleClient:
    client = socketio.AsyncSimpleClient()
    await client.connect(
        url, namespace="/messaging", auth={"token": token}, transports=["websocket"]
    )
    return client


async def hears_nothing(client: socketio.AsyncSimpleClient) -> None:
    with pytest.raises(socketio.exceptions.TimeoutError):
        await client.receive(timeout=QUIET)


def rest(url: str, headers: dict[str, str]) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=url, headers=headers)


async def open_dm(client, other_id) -> dict:
    response = await client.post("/api/v1/channels/dm", json={"userId": str(other_id)})
    assert response.status_code == 200, response.text
    return response.json()


async def make_channel(client, name="general", **body) -> dict:
    response = await client.post("/api/v1/channels", json={"name": name, **body})
    assert response.status_code == 201, response.text
    return response.json()


async def send(client, channel_id, body, **extra) -> dict:
    response = await client.post(
        f"/api/v1/channels/{channel_id}/messages", json={"body": body, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- who hears it (R10) -------------------------------------------------------------


async def test_a_first_rest_send_announces_the_dm_to_both_members(realtime_url, tokens):
    """Ada's two tabs and Grace hear it; Alan, and Ada in another workspace, do not.

    None of them has joined the DM's channel room, so what they hear came by their
    personal rooms.
    """
    async with rest(realtime_url, tokens.header()) as ada_rest:
        dm = await open_dm(ada_rest, tokens.GRACE)
        ada_tab_1 = await connected(realtime_url, tokens.mint())
        ada_tab_2 = await connected(realtime_url, tokens.mint())
        grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
        alan = await connected(realtime_url, tokens.mint(user_id=ALAN))
        ada_elsewhere = await connected(
            realtime_url, tokens.mint(workspace_id=tokens.OTHER_WORKSPACE)
        )

        await send(ada_rest, dm["id"], "hi")

        for listener in (ada_tab_1, ada_tab_2, grace):
            assert await listener.receive(timeout=WAIT) == [
                "channel_added",
                {"channelId": dm["id"]},
            ]
        await hears_nothing(alan)
        await hears_nothing(ada_elsewhere)

    for client in (ada_tab_1, ada_tab_2, grace, alan, ada_elsewhere):
        await client.disconnect()


async def test_a_first_socket_send_announces_the_dm(realtime_url, tokens):
    async with rest(realtime_url, tokens.header()) as ada_rest:
        dm = await open_dm(ada_rest, tokens.GRACE)
    sender = await connected(realtime_url, tokens.mint())
    ada_tab_2 = await connected(realtime_url, tokens.mint())
    grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
    alan = await connected(realtime_url, tokens.mint(user_id=ALAN))

    ack = await sender.call("send_message", {"channelId": dm["id"], "body": "hi"}, timeout=WAIT)

    assert ack["ok"] is True, ack
    for listener in (grace, ada_tab_2):
        assert await listener.receive(timeout=WAIT) == ["channel_added", {"channelId": dm["id"]}]
    await hears_nothing(alan)

    for client in (sender, ada_tab_2, grace, alan):
        await client.disconnect()


async def test_a_first_attachment_only_send_announces_the_dm(realtime_url_for, asset_stub, tokens):
    asset = asset_stub.ready()
    async with realtime_url_for(
        asset_internal_url=asset_stub.url, service_token_url=asset_stub.token_url
    ) as url:
        async with rest(url, tokens.header()) as ada_rest:
            dm = await open_dm(ada_rest, tokens.GRACE)
            grace = await connected(url, tokens.mint(user_id=tokens.GRACE))

            sent = await send(ada_rest, dm["id"], "", attachmentIds=[asset])

        assert sent["body"] == ""
        assert await grace.receive(timeout=WAIT) == ["channel_added", {"channelId": dm["id"]}]
        await grace.disconnect()


async def test_a_later_message_announces_nothing(realtime_url, tokens):
    """The first send's `channel_added` is asserted too, so a build that never emits fails here."""
    async with rest(realtime_url, tokens.header()) as ada_rest:
        dm = await open_dm(ada_rest, tokens.GRACE)
        grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
        assert (await grace.call("join_channel", dm["id"], timeout=WAIT))["ok"]

        await send(ada_rest, dm["id"], "first")
        # Commit, then publish: the message is announced to the room, then the DM to the person.
        assert (await grace.receive(timeout=WAIT))[0] == "message_received"
        assert await grace.receive(timeout=WAIT) == ["channel_added", {"channelId": dm["id"]}]

        await send(ada_rest, dm["id"], "second")
        event, payload = await grace.receive(timeout=WAIT)
        assert event == "message_received"
        assert payload["body"] == "second"
        await hears_nothing(grace)

    await grace.disconnect()


async def test_a_reply_does_not_announce_a_dm(realtime_url, tokens):
    """Only a top-level message opens a DM's listing; a thread reply is not a first message.

    Here the root went first, so the reply is the second thing sent — the guard is that
    `thread_root_id` is not what `opens_dm` counts. Grace hears the root's `channel_added`
    (asserted) and then only the reply's `message_received`.
    """
    async with rest(realtime_url, tokens.header()) as ada_rest:
        dm = await open_dm(ada_rest, tokens.GRACE)
        grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
        assert (await grace.call("join_channel", dm["id"], timeout=WAIT))["ok"]

        root = await send(ada_rest, dm["id"], "root")
        assert (await grace.receive(timeout=WAIT))[0] == "message_received"
        assert (await grace.receive(timeout=WAIT))[0] == "channel_added"

        await send(ada_rest, dm["id"], "a reply", threadRootId=root["id"])
        assert (await grace.receive(timeout=WAIT))[0] == "message_received"
        # A reply legitimately updates the thread summary (issue 3); what it must not do
        # is announce the DM again.
        assert (await grace.receive(timeout=WAIT))[0] == "thread_summary_changed"
        await hears_nothing(grace)

    await grace.disconnect()


async def test_a_first_message_announces_a_dm_and_not_a_channel(realtime_url, tokens):
    """The DM check, not "first", is what emits: a channel's first message announces nothing."""
    async with rest(realtime_url, tokens.header()) as ada_rest:
        dm = await open_dm(ada_rest, tokens.GRACE)
        general = await make_channel(ada_rest, "general")
        grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
        assert (await grace.call("join_channel", general["id"], timeout=WAIT))["ok"]

        await send(ada_rest, dm["id"], "private hello")
        assert await grace.receive(timeout=WAIT) == ["channel_added", {"channelId": dm["id"]}]

        await send(ada_rest, general["id"], "public hello")
        event, payload = await grace.receive(timeout=WAIT)
        assert event == "message_received"
        assert payload["channelId"] == general["id"]
        await hears_nothing(grace)

    await grace.disconnect()


async def test_two_first_messages_at_once_announce_the_dm_at_least_once(realtime_url, tokens):
    """Each send may see itself as first, so twice is allowed; never is not."""
    async with rest(realtime_url, tokens.header()) as ada_rest:
        dm = await open_dm(ada_rest, tokens.GRACE)
        grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
        async with rest(realtime_url, tokens.header(user_id=tokens.GRACE)) as grace_rest:
            await asyncio.gather(
                send(ada_rest, dm["id"], "from ada"), send(grace_rest, dm["id"], "from grace")
            )
            history = await grace_rest.get(f"/api/v1/channels/{dm['id']}/messages")

        assert await grace.receive(timeout=WAIT) == ["channel_added", {"channelId": dm["id"]}]
        assert sorted(m["body"] for m in history.json()["items"]) == ["from ada", "from grace"]

    await grace.disconnect()


# --- a third user (R11) -------------------------------------------------------------


@pytest.mark.parametrize(
    "event", ["join_channel", "send_message", "edit_message", "delete_message", "mark_read"]
)
async def test_a_third_user_cannot_use_a_dm_over_the_socket(realtime_url, tokens, event):
    async with rest(realtime_url, tokens.header()) as ada_rest:
        dm = await open_dm(ada_rest, tokens.GRACE)
        sent = await send(ada_rest, dm["id"], "private words")
        alan = await connected(realtime_url, tokens.mint(user_id=ALAN))
        payloads = {
            "join_channel": dm["id"],
            "send_message": {"channelId": dm["id"], "body": "let me in"},
            "edit_message": {
                "messageId": sent["id"],
                "body": "mine now",
                "version": sent["version"],
            },
            "delete_message": {"messageId": sent["id"]},
            "mark_read": {"channelId": dm["id"], "messageId": sent["id"]},
        }

        ack = await alan.call(event, payloads[event], timeout=WAIT)

        assert ack["ok"] is False, ack
        assert ack["problem"]["status"] == 404
        assert ack["problem"]["detail"] == "No such channel."
        # Ada's DM is as it was: one message, unedited and undeleted.
        history = (await ada_rest.get(f"/api/v1/channels/{dm['id']}/messages")).json()["items"]
        assert [(m["body"], m["deletedAt"]) for m in history] == [("private words", None)]

    await alan.disconnect()


async def test_typing_in_a_dm_reaches_the_other_member(realtime_url, tokens):
    async with rest(realtime_url, tokens.header()) as ada_rest:
        dm = await open_dm(ada_rest, tokens.GRACE)
    ada = await connected(realtime_url, tokens.mint())
    grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
    assert (await ada.call("join_channel", dm["id"], timeout=WAIT))["ok"]
    assert (await grace.call("join_channel", dm["id"], timeout=WAIT))["ok"]

    await ada.emit("typing", {"channelId": dm["id"]})
    event, payload = await grace.receive(timeout=WAIT)

    assert event == "user_typing"
    assert payload == {"channelId": dm["id"], "userId": str(tokens.ADA)}

    await ada.disconnect()
    await grace.disconnect()
