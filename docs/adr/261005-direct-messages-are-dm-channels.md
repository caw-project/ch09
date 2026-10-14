# Direct messages are `kind='dm'` channels, one per pair, listed on their first message

- **Status:** Accepted
- **Date:** 2026-10-05

## Context

Register D8b left DM modelling open with a working default of `kind='dm'` channels. The
`channels.kind` column accepted `dm` and `POST /channels` refused it, so nothing created or
listed one. Issue 5 builds the feature: any two people in a workspace can open the one DM they
share, it behaves like a private channel with two fixed members, it is named after the other
person, and it appears in both sidebars when its first message is sent.

Three things need deciding. What makes a DM unique per pair, when it is listed, and how the
other person's sidebar learns about it without a reload.

## Decision

A DM is a channel with `kind='dm'`. Its stored `name` is the **pair key** `dm:{low}:{high}`,
the two user ids sorted, and a partial unique index `ux_channels_dm_pair` on
`(workspace_id, name) WHERE kind = 'dm'` makes it unique per workspace. Get-or-create is
`POST /api/v1/channels/dm { userId }`: one `INSERT … ON CONFLICT DO NOTHING RETURNING id`, then
a `SELECT` if no row came back. Members are inserted only by the transaction that created the
channel. It answers 200 either way.

Both people get a `member` row and nobody an `admin` row, so nothing can rename, archive or
re-member a DM (403, whatever the caller's role) and only an author deletes a message in one.
Everything else works as in a private channel; a person outside the pair gets 404.

`GET /channels` lists a DM only once it has a top-level message, a tombstone counting. The rule
is in `list_page`, not in the visibility query, so an empty DM stays reachable by URL and by
`join_channel`. `ChannelResponse` gains `dmPartnerId`, computed per caller from the pair key.

The first top-level send into a DM, by REST or socket, emits `channel_added { channelId }` to
both members' personal rooms after `message_received`. The SPA refetches its channel list on it.
The check runs before the insert, in the send's transaction, so the first message to commit
always emits; two concurrent first sends may both emit, which costs one extra request.

## Consequences

One DM per pair is a database guarantee, not a check, so racing opens cannot split a
conversation. The pair key lives in a column that is otherwise unused for a DM, which needs no
migration of data. The partner is a pure parse of the name, so a DM costs no join.

Messaging does not check that `userId` is a member of the workspace, as add-member does not
(register D44). A DM with an id that names no one is an inert row nobody else can see.

The sidebar reads one 50-row page of `GET /channels`, and DMs now share it with channels. A
large workspace can push rows off it; paging the sidebar is its own change.

A rename of a user, or removal from the workspace, leaves their DMs as they are.

## Alternatives Considered

### A `dm_pair` column with a CHECK

One more column for what `name` already carries and a rename can never change. Moving to it
later is a migration that copies `name` into it.

### Check, then insert

Two statements with a gap between them, and two people opening a DM at once is the case that
matters. `channels.create` leaves names to its index for the same reason.

### List a DM as soon as it is opened

An empty DM in the other person's sidebar with nothing in it is a notification with no content,
and every opened-and-abandoned picker click would leave one behind.

### 201 for created, 200 for found

Two racing callers would get different codes for the same outcome, and the client never needs
to know which happened.
