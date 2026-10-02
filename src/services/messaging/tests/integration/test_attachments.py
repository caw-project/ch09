"""Sending a message with attachments, and downloading them (issue 4 R6-R8, R10, R12).

Messaging at its public boundary — REST and Socket.IO — against real Postgres
and Redis, with Asset's internal API stood in by `asset_stub` (built from
`contracts.assets`, and proven against the real routes in Asset's own tests).

The rule most of these defend: **the message is inserted only after the claim**,
and a refused or unreachable claim leaves nothing behind — so each failure test
ends on an empty history, and each is paired with the send that does succeed.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import socketio

PROBLEM = "application/problem+json"
WAIT = 5
UNAVAILABLE = "Attachments can't be checked right now. Nothing was sent."


async def connected(url: str, token: str) -> socketio.AsyncSimpleClient:
    client = socketio.AsyncSimpleClient()
    await client.connect(
        url, namespace="/messaging", auth={"token": token}, transports=["websocket"]
    )
    return client


async def make_channel(client, headers, name="general", **body):
    response = await client.post("/api/v1/channels", json={"name": name, **body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def send(client, headers, channel_id, body="", ids=()):
    return await client.post(
        f"/api/v1/channels/{channel_id}/messages",
        json={"body": body, "attachmentIds": [str(i) for i in ids]},
        headers=headers,
    )


async def history(client, headers, channel_id):
    response = await client.get(f"/api/v1/channels/{channel_id}/messages", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def download(client, headers, message_id, asset_id):
    return client.get(
        f"/api/v1/messages/{message_id}/attachments/{asset_id}/download-url", headers=headers
    )


@pytest.fixture
def with_asset(client_for, asset_stub):
    """A client whose Messaging is pointed at `asset_stub` for both Asset and the token."""

    def build():
        return client_for(asset_internal_url=asset_stub.url, service_token_url=asset_stub.token_url)

    return build


# --- sending ----------------------------------------------------------------


async def test_rest_send_carries_attachments_in_order(with_asset, asset_stub, ada):
    """R6, R8: breaks if the order is the claim's, the database's, or lost on the way to history."""
    png = asset_stub.ready("diagram.png", "image/png", 1000)
    pdf = asset_stub.ready("notes.pdf", "application/pdf", 2000)
    expected = [asset_stub.metadata[pdf], asset_stub.metadata[png]]

    async with with_asset() as client:
        channel = await make_channel(client, ada)
        created = await send(client, ada, channel["id"], "the plans", [pdf, png])
        listed = await history(client, ada, channel["id"])
        single = await client.get(f"/api/v1/messages/{created.json()['id']}", headers=ada)

    assert created.status_code == 201, created.text
    assert created.json()["attachments"] == expected
    assert [m["attachments"] for m in listed] == [expected]
    assert single.json()["attachments"] == expected


async def test_ten_attachments_are_accepted(with_asset, asset_stub, ada):
    """The positive for the eleven-is-refused guard below: ten is the bound, not nine."""
    ids = [asset_stub.ready(f"{n}.png") for n in range(10)]

    async with with_asset() as client:
        channel = await make_channel(client, ada)
        response = await send(client, ada, channel["id"], "ten", ids)

    assert response.status_code == 201, response.text
    assert [a["assetId"] for a in response.json()["attachments"]] == ids


async def test_socket_send_acks_attachments_and_broadcasts_them(
    realtime_url_for, asset_stub, tokens, ada
):
    """R8: the ack and the broadcast are the same message, attachments included."""
    png = asset_stub.ready("diagram.png")
    pdf = asset_stub.ready("notes.pdf", "application/pdf")
    expected = [asset_stub.metadata[png], asset_stub.metadata[pdf]]

    async with realtime_url_for(
        asset_internal_url=asset_stub.url, service_token_url=asset_stub.token_url
    ) as url:
        async with httpx.AsyncClient(base_url=url, headers=ada) as rest:
            channel = await make_channel(rest, {})
        sender = await connected(url, tokens.mint())
        watcher = await connected(url, tokens.mint(user_id=tokens.GRACE))
        assert (await watcher.call("join_channel", channel["id"], timeout=WAIT))["ok"]

        ack = await sender.call(
            "send_message",
            {"channelId": channel["id"], "body": "the plans", "attachmentIds": [png, pdf]},
            timeout=WAIT,
        )
        event, payload = await watcher.receive(timeout=WAIT)
        await sender.disconnect()
        await watcher.disconnect()

    assert ack["ok"] is True, ack
    assert ack["data"]["attachments"] == expected
    assert event == "message_received"
    assert payload == ack["data"]


async def test_a_body_may_be_empty_only_with_an_attachment(with_asset, asset_stub, ada):
    """R6, guard and positive together: the same empty body is refused alone and sent with a file."""
    asset = asset_stub.ready()

    async with with_asset() as client:
        channel = await make_channel(client, ada)
        alone = await send(client, ada, channel["id"], "")
        empty_history = await history(client, ada, channel["id"])
        with_file = await send(client, ada, channel["id"], "", [asset])

    assert alone.status_code == 400
    assert alone.json()["errors"]["body"] == ["A message cannot be empty."]
    assert empty_history == []
    assert with_file.status_code == 201, with_file.text
    assert with_file.json()["body"] == ""


async def test_eleven_ids_are_400(client, ada):
    """R2: refused before any call to Asset — there is no stub, and nothing is saved."""
    channel = await make_channel(client, ada)

    response = await send(client, ada, channel["id"], "too many", [uuid.uuid4() for _ in range(11)])

    assert response.status_code == 400
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["errors"]["attachmentIds"]
    assert await history(client, ada, channel["id"]) == []


async def test_a_duplicate_id_is_400(client, ada):
    """Decision 26 (assumed): a repeated id is refused outright, before any call to Asset."""
    channel = await make_channel(client, ada)
    repeated = uuid.uuid4()

    response = await send(client, ada, channel["id"], "twice", [repeated, repeated])

    assert response.status_code == 400
    assert response.json()["errors"]["attachmentIds"] == ["An attachment is listed twice."]
    assert await history(client, ada, channel["id"]) == []


# --- refusals ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("reason", "detail"),
    [
        ("not-found", "An attachment could not be found."),
        ("not-yours", "An attachment was uploaded by someone else."),
        ("not-ready", "An attachment has not finished uploading."),
        ("already-attached", "An attachment is already on another message."),
    ],
)
async def test_a_refused_claim_is_409_and_nothing_is_saved(
    reason, detail, with_asset, asset_stub, ada
):
    """R7: the whole send is refused with the reason in words, and no message exists."""
    fine = asset_stub.ready("fine.png")
    refused = asset_stub.ready("refused.png")
    asset_stub.refusals[refused] = reason

    async with with_asset() as client:
        channel = await make_channel(client, ada)
        response = await send(client, ada, channel["id"], "one bad apple", [fine, refused])
        saved = await history(client, ada, channel["id"])

    assert response.status_code == 409
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["detail"] == detail
    assert saved == []


async def test_a_retry_after_a_lost_ack_is_already_attached(with_asset, asset_stub, ada):
    """The timeline: the first send was saved, so the retry is refused and the message stays once."""
    asset = asset_stub.ready()

    async with with_asset() as client:
        channel = await make_channel(client, ada)
        first = await send(client, ada, channel["id"], "the plans", [asset])
        retry = await send(client, ada, channel["id"], "the plans", [asset])
        saved = await history(client, ada, channel["id"])

    assert first.status_code == 201
    assert retry.status_code == 409
    assert retry.json()["detail"] == "An attachment is already on another message."
    assert [m["id"] for m in saved] == [first.json()["id"]]


@pytest.mark.parametrize("transport", ["rest", "socket"])
async def test_asset_down_is_503_and_nothing_is_saved(
    transport, realtime_url_for, asset_stub, tokens, ada
):
    """R7: an unreachable Asset refuses the send on both transports, and the same send then works."""
    asset = asset_stub.ready()
    asset_stub.down = True

    async with (
        realtime_url_for(
            asset_internal_url=asset_stub.url, service_token_url=asset_stub.token_url
        ) as url,
        httpx.AsyncClient(base_url=url, headers=ada) as rest,
    ):
        channel = await make_channel(rest, {})
        if transport == "rest":
            response = await send(rest, {}, channel["id"], "the plans", [asset])
            status, problem = response.status_code, response.json()
        else:
            sender = await connected(url, tokens.mint())
            ack = await sender.call(
                "send_message",
                {"channelId": channel["id"], "body": "the plans", "attachmentIds": [asset]},
                timeout=WAIT,
            )
            await sender.disconnect()
            assert ack["ok"] is False
            status, problem = ack["problem"]["status"], ack["problem"]
        saved = await history(rest, {}, channel["id"])

        asset_stub.down = False
        recovered = await send(rest, {}, channel["id"], "the plans", [asset])

    assert status == 503
    assert problem["detail"] == UNAVAILABLE
    assert saved == []
    assert recovered.status_code == 201, recovered.text


async def test_token_endpoint_down_is_503(client_for, ada):
    """R7, Decided 3: no token means no claim, so the send is refused the same way."""
    async with client_for(
        asset_internal_url="http://asset.invalid", service_token_url="http://auth.invalid/token"
    ) as client:
        channel = await make_channel(client, ada)
        response = await send(client, ada, channel["id"], "the plans", [uuid.uuid4()])
        saved = await history(client, ada, channel["id"])

    assert response.status_code == 503
    assert response.json()["detail"] == UNAVAILABLE
    assert saved == []


# --- the claim --------------------------------------------------------------


async def test_the_claim_carries_the_callers_workspace_and_the_new_message_id(
    with_asset, asset_stub, ada, tokens
):
    """CH001 and claim-then-insert: the claim names the token's workspace and the message's own id."""
    asset = asset_stub.ready()

    async with with_asset() as client:
        channel = await make_channel(client, ada)
        created = await send(client, ada, channel["id"], "the plans", [asset])

    (claim,) = asset_stub.claims
    assert claim["workspaceId"] == str(tokens.WORKSPACE)
    assert claim["userId"] == str(tokens.ADA)
    assert claim["assetIds"] == [asset]
    # The id was chosen before the claim and is the one the message was inserted with.
    assert claim["messageId"] == created.json()["id"]
    assert claim["authorization"].startswith("Bearer stub-token-")


async def test_a_send_with_no_attachments_makes_no_claim(with_asset, asset_stub, ada):
    """Breaks if every send pays a round trip (and a token fetch) to Asset."""
    async with with_asset() as client:
        channel = await make_channel(client, ada)
        response = await send(client, ada, channel["id"], "just words")

    assert response.status_code == 201
    assert asset_stub.claims == []
    assert asset_stub.token_calls == 0


async def test_the_token_is_reused_across_sends(with_asset, asset_stub, ada):
    """Decided 3: one `/token` call serves two sends, and both claims carry that token."""
    first, second = asset_stub.ready("a.png"), asset_stub.ready("b.png")

    async with with_asset() as client:
        channel = await make_channel(client, ada)
        await send(client, ada, channel["id"], "one", [first])
        await send(client, ada, channel["id"], "two", [second])

    assert asset_stub.token_calls == 1
    assert [c["authorization"] for c in asset_stub.claims] == ["Bearer stub-token-1"] * 2


# --- tombstones and edits ---------------------------------------------------


async def test_a_deleted_message_shows_no_attachments(realtime_url_for, asset_stub, tokens, ada):
    """R12: REST, the `message_deleted` payload and history all drop the attachments."""
    asset = asset_stub.ready()

    async with (
        realtime_url_for(
            asset_internal_url=asset_stub.url, service_token_url=asset_stub.token_url
        ) as url,
        httpx.AsyncClient(base_url=url, headers=ada) as rest,
    ):
        channel = await make_channel(rest, {})
        watcher = await connected(url, tokens.mint(user_id=tokens.GRACE))
        assert (await watcher.call("join_channel", channel["id"], timeout=WAIT))["ok"]
        sent = (await send(rest, {}, channel["id"], "the plans", [asset])).json()
        await watcher.receive(timeout=WAIT)
        before = (await history(rest, {}, channel["id"]))[0]

        deleted = await rest.delete(f"/api/v1/messages/{sent['id']}")
        event, payload = await watcher.receive(timeout=WAIT)
        after = (await history(rest, {}, channel["id"]))[0]
        await watcher.disconnect()

    # The guard's positive: the attachments were there to be removed.
    assert len(sent["attachments"]) == 1
    assert len(before["attachments"]) == 1
    assert deleted.status_code == 200
    assert deleted.json()["attachments"] == []
    assert event == "message_deleted"
    assert payload["attachments"] == []
    assert after["attachments"] == []


async def test_an_edit_keeps_the_attachments(with_asset, asset_stub, ada):
    """R12: breaks if an edit rebuilds the message without them."""
    asset = asset_stub.ready()

    async with with_asset() as client:
        channel = await make_channel(client, ada)
        sent = (await send(client, ada, channel["id"], "the plans", [asset])).json()
        edited = await client.patch(
            f"/api/v1/messages/{sent['id']}",
            json={"body": "the new plans", "version": sent["version"]},
            headers=ada,
        )
        saved = await history(client, ada, channel["id"])

    assert edited.status_code == 200, edited.text
    assert edited.json()["body"] == "the new plans"
    assert edited.json()["attachments"] == sent["attachments"] != []
    assert saved[0]["attachments"] == sent["attachments"]


# --- the download route -----------------------------------------------------


async def test_download_url_for_an_invisible_channel_is_404(client, ada, grace):
    """R10: a private channel's message answers Grace as if the channel did not exist."""
    channel = await make_channel(client, ada, "launch-plans", kind="private")
    message = (await send(client, ada, channel["id"], "secret")).json()

    response = await download(client, grace, message["id"], uuid.uuid4())

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["detail"] == "No such channel."


async def test_download_url_for_a_visible_message(with_asset, asset_stub, ada, grace, tokens):
    """R10: anyone who can see the channel gets a URL, and Asset is asked with the message's own ids."""
    asset = asset_stub.ready()

    async with with_asset() as client:
        channel = await make_channel(client, ada)
        sent = (await send(client, ada, channel["id"], "the plans", [asset])).json()
        response = await download(client, grace, sent["id"], asset)

    assert response.status_code == 200, response.text
    assert response.json()["url"].startswith("http://garage.test/")
    assert response.json()["expiresAt"]
    assert asset_stub.downloads[-1] == {
        "assetId": asset,
        "workspaceId": str(tokens.WORKSPACE),
        "messageId": sent["id"],
    }


async def test_download_url_for_a_deleted_message_is_404(with_asset, asset_stub, ada):
    """R10: Asset would still mint the URL, so only Messaging's own tombstone check can refuse."""
    asset = asset_stub.ready()

    async with with_asset() as client:
        channel = await make_channel(client, ada)
        sent = (await send(client, ada, channel["id"], "the plans", [asset])).json()
        before = await download(client, ada, sent["id"], asset)
        await client.delete(f"/api/v1/messages/{sent['id']}", headers=ada)
        after = await download(client, ada, sent["id"], asset)

    assert before.status_code == 200
    assert after.status_code == 404
    assert after.json()["detail"] == "No such attachment."


async def test_download_url_for_an_asset_not_on_the_message_is_404(with_asset, asset_stub, ada):
    """R10: Messaging's own record decides — the stub would mint a URL for this asset, and is not asked."""
    on_message = asset_stub.ready("mine.png")
    elsewhere = asset_stub.ready("elsewhere.png")

    async with with_asset() as client:
        channel = await make_channel(client, ada)
        sent = (await send(client, ada, channel["id"], "the plans", [on_message])).json()
        asset_stub.claimed_by[elsewhere] = sent["id"]
        calls_before = len(asset_stub.downloads)
        response = await download(client, ada, sent["id"], elsewhere)

    assert response.status_code == 404
    assert response.json()["detail"] == "No such attachment."
    assert len(asset_stub.downloads) == calls_before


async def test_download_url_with_asset_down_is_503(with_asset, asset_stub, ada):
    asset = asset_stub.ready()

    async with with_asset() as client:
        channel = await make_channel(client, ada)
        sent = (await send(client, ada, channel["id"], "the plans", [asset])).json()
        asset_stub.down = True
        response = await download(client, ada, sent["id"], asset)

    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM
