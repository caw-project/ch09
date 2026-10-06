"""Direct messages over REST, against a real Postgres (issue 5, R1 to R9 and R11).

A DM is a `kind='dm'` channel keyed by its pair of users. What only a database
can answer is here: that one pair is one row however many people open it at
once, that an empty DM is unlisted while a tombstoned one is not, and that every
route a private channel has answers a member and refuses everyone else.

The pure rules (the key, the partner) are in `tests/unit/test_dms.py`. Every test
here reaches `open_dm` first, so before the route exists each fails there, at
`assert 405 == 200`: the path matches `/{channel_id}`, which has no POST.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text

ALAN = uuid.uuid4()

CANT_CHANGE = "A direct message can't be renamed, archived or have its members changed."
NOT_ADMIN = "Only a channel admin can do that."
NOT_AUTHOR = "Only the author or a channel admin can delete a message."


@pytest.fixture
def alan(tokens) -> dict[str, str]:
    return tokens.header(user_id=ALAN, name="Alan Turing", email="alan@collabhub.dev")


async def open_dm(client, headers, other_id) -> dict:
    response = await client.post(
        "/api/v1/channels/dm", json={"userId": str(other_id)}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def make_channel(client, headers, name="general", **body) -> dict:
    response = await client.post("/api/v1/channels", json={"name": name, **body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def send(client, headers, channel_id, body, **extra) -> dict:
    response = await client.post(
        f"/api/v1/channels/{channel_id}/messages", json={"body": body, **extra}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def listed(client, headers) -> list[dict]:
    response = await client.get("/api/v1/channels", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def listed_ids(client, headers) -> list[str]:
    return [c["id"] for c in await listed(client, headers)]


async def dm_count(engine) -> int:
    async with engine.connect() as connection:
        return await connection.scalar(text("SELECT count(*) FROM channels WHERE kind = 'dm'"))


# --- one per pair (R2) -------------------------------------------------------------


async def test_opening_twice_either_way_round_is_one_dm(client, ada, grace, tokens, engine):
    first = await open_dm(client, ada, tokens.GRACE)
    again = await open_dm(client, ada, tokens.GRACE)
    from_grace = await open_dm(client, grace, tokens.ADA)

    assert first["id"] == again["id"] == from_grace["id"]
    assert first["kind"] == "dm"
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text("SELECT user_id, role FROM channel_members WHERE channel_id = :id"),
                {"id": first["id"]},
            )
        ).all()
    # Both people are members, and nobody is an admin (decision 11).
    assert {(str(user), role) for user, role in rows} == {
        (str(tokens.ADA), "member"),
        (str(tokens.GRACE), "member"),
    }


async def test_opening_at_once_is_one_dm(client, ada, grace, tokens, engine):
    """Ten opens, five from each side, all in flight together — one row, one id."""
    opens = [
        client.post("/api/v1/channels/dm", json={"userId": str(tokens.GRACE)}, headers=ada)
        for _ in range(5)
    ] + [
        client.post("/api/v1/channels/dm", json={"userId": str(tokens.ADA)}, headers=grace)
        for _ in range(5)
    ]

    responses = await asyncio.gather(*opens)

    assert [r.status_code for r in responses] == [200] * 10, [r.text for r in responses]
    assert len({r.json()["id"] for r in responses}) == 1
    assert await dm_count(engine) == 1
    async with engine.connect() as connection:
        members = await connection.scalar(text("SELECT count(*) FROM channel_members"))
    assert members == 2


async def test_the_same_pair_in_another_workspace_is_another_dm(client, ada, tokens):
    here = await open_dm(client, ada, tokens.GRACE)
    elsewhere = tokens.header(workspace_id=tokens.OTHER_WORKSPACE)

    there = await open_dm(client, elsewhere, tokens.GRACE)

    assert there["id"] != here["id"]


# --- not with yourself (R3) ---------------------------------------------------------


async def test_a_dm_with_yourself_is_refused_and_nothing_is_written(client, ada, tokens, engine):
    # The positive half first: opening with someone else is fine.
    await open_dm(client, ada, tokens.GRACE)
    assert await dm_count(engine) == 1

    response = await client.post(
        "/api/v1/channels/dm", json={"userId": str(tokens.ADA)}, headers=ada
    )

    assert response.status_code == 400
    problem = response.json()
    assert problem["detail"] == "You can't start a direct message with yourself."
    assert "userId" in problem["errors"]
    assert await dm_count(engine) == 1


# --- any role (R4) ------------------------------------------------------------------


async def test_any_workspace_role_may_open_a_dm(client, tokens):
    admin = tokens.header(roles=("admin",))
    member = tokens.header(user_id=tokens.GRACE, name="Grace Hopper", roles=("member",))

    from_admin = await open_dm(client, admin, tokens.GRACE)
    from_member = await open_dm(client, member, tokens.ADA)

    assert from_admin["id"] == from_member["id"]


# --- listing (R5, R6) ---------------------------------------------------------------


async def test_an_empty_dm_is_not_listed_for_either_member(client, ada, grace, tokens):
    # An empty public channel in the same response proves the list isn't just empty.
    empty_public = await make_channel(client, ada, "general")
    dm = await open_dm(client, ada, tokens.GRACE)

    for headers in (ada, grace):
        ids = await listed_ids(client, headers)
        assert empty_public["id"] in ids
        assert dm["id"] not in ids
    # Reachable by URL all the same.
    response = await client.get(f"/api/v1/channels/{dm['id']}", headers=grace)
    assert response.status_code == 200


async def test_a_dm_is_listed_for_both_once_it_has_a_message(client, ada, grace, tokens):
    dm = await open_dm(client, ada, tokens.GRACE)
    await send(client, ada, dm["id"], "hi")

    ada_row = next(c for c in await listed(client, ada) if c["id"] == dm["id"])
    grace_row = next(c for c in await listed(client, grace) if c["id"] == dm["id"])

    assert grace_row["unreadCount"] == 1
    assert ada_row["unreadCount"] == 0


async def test_the_listing_rule_is_per_dm(client, ada, tokens):
    """Ada has one DM with a message and one without: only the first is listed.

    Breaks if the rule is "the caller has any DM with a message" rather than this DM's own.
    """
    live = await open_dm(client, ada, tokens.GRACE)
    empty = await open_dm(client, ada, ALAN)
    await send(client, ada, live["id"], "root")

    ids = await listed_ids(client, ada)

    assert live["id"] in ids
    assert empty["id"] not in ids


async def test_a_dm_whose_only_message_is_deleted_stays_listed(client, ada, grace, tokens):
    dm = await open_dm(client, ada, tokens.GRACE)
    sent = await send(client, ada, dm["id"], "oops")

    deleted = await client.delete(f"/api/v1/messages/{sent['id']}", headers=ada)

    assert deleted.status_code == 200
    assert deleted.json()["deletedAt"] is not None
    assert dm["id"] in await listed_ids(client, ada)
    assert dm["id"] in await listed_ids(client, grace)


# --- the partner (R7) ---------------------------------------------------------------


async def test_each_member_sees_the_other_as_partner(client, ada, grace, tokens):
    general = await make_channel(client, ada, "general")
    from_ada = await open_dm(client, ada, tokens.GRACE)
    from_grace = await open_dm(client, grace, tokens.ADA)
    await send(client, ada, from_ada["id"], "hi")

    assert from_ada["dmPartnerId"] == str(tokens.GRACE)
    assert from_grace["dmPartnerId"] == str(tokens.ADA)
    for headers, partner in ((ada, tokens.GRACE), (grace, tokens.ADA)):
        one = await client.get(f"/api/v1/channels/{from_ada['id']}", headers=headers)
        assert one.json()["dmPartnerId"] == str(partner)
        row = next(c for c in await listed(client, headers) if c["id"] == from_ada["id"])
        assert row["dmPartnerId"] == str(partner)
        public = next(c for c in await listed(client, headers) if c["id"] == general["id"])
        assert public["dmPartnerId"] is None


# --- fixed membership (R9) ----------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        pytest.param("PATCH", "/channels/{dm}", {"version": 0, "name": "renamed"}, id="rename"),
        pytest.param("PATCH", "/channels/{dm}", {"version": 0, "topic": "ours"}, id="topic"),
        pytest.param("DELETE", "/channels/{dm}", None, id="archive"),
        pytest.param("POST", "/channels/{dm}/members", {"userId": str(ALAN)}, id="add-member"),
        pytest.param("DELETE", "/channels/{dm}/members/{grace}", None, id="remove-member"),
    ],
)
async def test_a_dm_cannot_be_changed(client, ada, tokens, method, path, body):
    """403 with its own reason — not "Only a channel admin can do that.", which is what a
    member's `myRole` would give today, and would stop being true if admin-gating relaxed."""
    dm = await open_dm(client, ada, tokens.GRACE)
    url = "/api/v1" + path.format(dm=dm["id"], grace=tokens.GRACE)

    response = await client.request(method, url, json=body, headers=ada)

    assert response.status_code == 403
    assert response.json()["detail"] == CANT_CHANGE
    assert response.json()["detail"] != NOT_ADMIN
    # Nothing moved.
    after = await client.get(f"/api/v1/channels/{dm['id']}", headers=ada)
    assert after.json()["name"] == dm["name"]
    assert after.json()["topic"] == dm["topic"]
    members = await client.get(f"/api/v1/channels/{dm['id']}/members", headers=ada)
    assert len(members.json()["items"]) == 2


# --- works like a private channel (R8) ----------------------------------------------


async def test_only_the_author_deletes_in_a_dm(client, ada, grace, tokens):
    dm = await open_dm(client, ada, tokens.GRACE)
    sent = await send(client, ada, dm["id"], "mine")

    refused = await client.delete(f"/api/v1/messages/{sent['id']}", headers=grace)
    still = await client.get(f"/api/v1/messages/{sent['id']}", headers=ada)
    allowed = await client.delete(f"/api/v1/messages/{sent['id']}", headers=ada)

    assert refused.status_code == 403
    assert refused.json()["detail"] == NOT_AUTHOR
    assert still.json()["deletedAt"] is None
    assert allowed.status_code == 200


async def test_both_members_can_use_every_message_route(client, ada, grace, tokens):
    dm = await open_dm(client, ada, tokens.GRACE)
    root = await send(client, ada, dm["id"], "root")

    sent = await send(client, grace, dm["id"], "from grace")
    history = await client.get(f"/api/v1/channels/{dm['id']}/messages", headers=grace)
    edited = await client.patch(
        f"/api/v1/messages/{sent['id']}",
        json={"body": "from grace, edited", "version": sent["version"]},
        headers=grace,
    )
    reacted = await client.post(
        f"/api/v1/messages/{root['id']}/reactions", json={"emoji": "tada"}, headers=grace
    )
    reply = await send(client, grace, dm["id"], "a reply", threadRootId=root["id"])
    thread = await client.get(f"/api/v1/messages/{root['id']}/thread", headers=grace)
    marked = await client.post(
        f"/api/v1/channels/{dm['id']}/read", json={"messageId": root["id"]}, headers=grace
    )
    members = await client.get(f"/api/v1/channels/{dm['id']}/members", headers=grace)

    assert history.status_code == 200
    assert [m["body"] for m in history.json()["items"]] == ["from grace", "root"]
    assert edited.status_code == 200
    assert edited.json()["body"] == "from grace, edited"
    assert reacted.status_code == 200
    assert reacted.json()["reactions"][0]["emoji"] == "tada"
    assert thread.status_code == 200
    assert [m["id"] for m in thread.json()["items"]] == [reply["id"]]
    assert marked.status_code == 204
    assert members.status_code == 200
    assert len(members.json()["items"]) == 2


# --- private (R11) ------------------------------------------------------------------

ASSET = uuid.uuid4()


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        pytest.param("GET", "/channels/{dm}", None, id="get-channel"),
        pytest.param("GET", "/channels/{dm}/messages", None, id="history"),
        pytest.param("POST", "/channels/{dm}/messages", {"body": "let me in"}, id="send"),
        pytest.param(
            "POST",
            "/channels/{dm}/messages",
            {"body": "a reply", "threadRootId": "{msg}"},
            id="reply",
        ),
        pytest.param("GET", "/channels/{dm}/members", None, id="members"),
        pytest.param("POST", "/channels/{dm}/read", {"messageId": "{msg}"}, id="mark-read"),
        pytest.param("PATCH", "/channels/{dm}", {"version": 0, "name": "mine"}, id="rename"),
        pytest.param("DELETE", "/channels/{dm}", None, id="archive"),
        pytest.param("POST", "/channels/{dm}/members", {"userId": str(ALAN)}, id="add-member"),
        pytest.param("DELETE", "/channels/{dm}/members/{ada}", None, id="remove-member"),
        pytest.param("GET", "/messages/{msg}", None, id="get-message"),
        pytest.param("GET", "/messages/{msg}/thread", None, id="thread"),
        pytest.param("PATCH", "/messages/{msg}", {"body": "mine now", "version": 0}, id="edit"),
        pytest.param("DELETE", "/messages/{msg}", None, id="delete"),
        pytest.param("POST", "/messages/{msg}/reactions", {"emoji": "tada"}, id="react"),
        pytest.param("DELETE", "/messages/{msg}/reactions/tada", None, id="unreact"),
        pytest.param(
            "GET", f"/messages/{{msg}}/attachments/{ASSET}/download-url", None, id="download-url"
        ),
    ],
)
async def test_a_third_user_gets_404_on_every_route(
    client, ada, grace, alan, tokens, method, path, body
):
    """Alan is in the workspace and in neither side of the DM: 404 "No such channel.", never 403.

    A real message exists, so a route that checked only that the message is real would let him in.
    """
    dm = await open_dm(client, ada, tokens.GRACE)
    root = await send(client, ada, dm["id"], "private words")
    await send(client, grace, dm["id"], "a reply from grace", threadRootId=root["id"])
    # A visible channel for Alan, so a route that returned early on "sees nothing" isn't mistaken
    # for the DM rule.
    await make_channel(client, ada, "general")

    def fill(value):
        if isinstance(value, dict):
            return {k: fill(v) for k, v in value.items()}
        if isinstance(value, str):
            return value.format(dm=dm["id"], msg=root["id"], ada=tokens.ADA)
        return value

    response = await client.request(
        method, "/api/v1" + fill(path), json=fill(body) if body is not None else None, headers=alan
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "No such channel."
    # The message is untouched and the DM is still two people.
    still = await client.get(f"/api/v1/messages/{root['id']}", headers=ada)
    assert still.json()["body"] == "private words"
    assert still.json()["deletedAt"] is None
    assert still.json()["reactions"] == []
    members = await client.get(f"/api/v1/channels/{dm['id']}/members", headers=ada)
    assert len(members.json()["items"]) == 2
