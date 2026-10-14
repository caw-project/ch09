Issue: 5

# Issue 5 — Direct messages

## Summary

Any two people in a workspace can message each other privately. A **+** beside a new *Direct
messages* section in the sidebar opens a picker of workspace members; picking someone opens the
one DM the pair shares, creating it the first time. A DM works like a private channel with two
fixed members — history, threads, reactions, attachments, typing, unread and search — and is
named everywhere after the other person. It appears in both people's sidebars, live, when its
first message is sent.

DMs are `kind='dm'` channels, the 🟡 default of register **D8b**; this issue builds on it and
settles it.

**Built from `main`.** No sibling feature branch is unmerged.

## Services touched

**Messaging and the SPA.** Read `docs/design/02-messaging-service.md` §3.1 (endpoint table,
§3.1.2, §3.1.3 DTO), §3.2 and §4, and `docs/design/06-frontend-spa.md` §3, §5.2 and §5.4. No
Auth, Worker, Asset, chart or Compose change.

## What exists already

- **`channels.kind`** is a free `text` column, default `'public'`, with **no CHECK constraint**
  (`models.py:99`, `alembic/versions/0001_channels.py`). `models.py:56-62` defines `DM = "dm"`
  (unused) and `CREATABLE_KINDS = (PUBLIC, PRIVATE)`; `channels.validate_kind` refuses `dm` with
  a 400 (`routers/channels.py:168-172`), and unit and integration tests pin that refusal
  (`test_channel_rules.py:94-98`, `test_channels.py:170-174`) — they change with this issue.
- **`channels.name` is `NOT NULL`** and validated (`channels.validate_name`, 3–80 chars,
  `^[A-Za-z][A-Za-z0-9-]*$`). `ux_channels_public_name` is unique only `WHERE kind = 'public'`.
  Doc 02 §3.1.2 says "a DM has no name and no creator-as-admin".
- **`channel_members`** — PK `(channel_id, user_id)`, `role` admin | member. Nothing makes a
  *pair* of users unique.
- **Visibility is one query**, `channels._visible_query` (`channels.py:337-360`): same `wsp`,
  not archived, and `kind = 'public' OR` a membership row. Every non-public kind is already
  member-only. History, both send paths, threads, reactions, attachment download-url, read state,
  `join_channel`, `typing` and search (`channels.visible_ids`) all go through it.
- **Admin gating:** `_admin_or_403` (`routers/channels.py:117-124`) guards rename, archive and
  member writes; `messages.check_deletable` allows the author or a channel admin.
- **`GET /channels`** lists visible channels, cursor-paged on `(name, id)`, with `unreadCount`
  and `lastReadId` on every row. **`ChannelResponse`** has no member list and no `workspaceId`.
- **Rooms:** `channel:{id}`, and `user:{workspaceId}:{userId}` (`realtime.reader_room`), which
  every connection joins on connect and which today carries only `read_receipt_updated`.
  **Nothing emits when a channel is created or a member added.**
- **Messaging never calls Auth for users.** `POST /channels/{id}/members` accepts any `userId`
  unchecked. Workspace member removal publishes nothing.
- **SPA:** `ChannelList.tsx` is one flat list with a hard-coded `#`; `channelKeys.list(ws)` polls
  every 30 s, and is invalidated on socket connect, channel switch, focus and visibility
  (`useChannels.ts`, `useChannelSocket.ts:143`). Names come from Auth through
  `useWorkspaceMembers` (`directoryKeys.members(ws)`), and `nameFor(id)` falls back to an
  8-char `shortId`. `#` is also hard-coded in `ChannelHeader`, the composer placeholder
  (`Message #…`) and `SearchResult`; `useChannelNames` resolves search's channel names.
  `ChannelView` shows `MemberPanel` in its right column.
- **Template:** threads (`c2ca4e3`) — a migration, domain rules, DTO fields, a new broadcast, a
  socket handler and cache writer, a BDD journey.

## Requirements

1. **Start a DM.** A **+** in the sidebar's *Direct messages* section opens a picker of the
   current workspace's members, excluding the caller. Picking someone navigates to `/c/{id}` of
   the DM the pair shares, creating it if none exists.
2. **One per pair.** A pair of users has exactly one DM in a workspace, whoever opens it and in
   either order — including when both open it at the same instant.
3. **Not with yourself.** Opening a DM with your own id is refused; nothing is created.
4. **Any role.** Any two members of the workspace may share a DM, whatever their workspace role.
5. **Listed once it has a message.** A DM appears in `GET /channels` — for both members — only
   once it has at least one top-level message. A deleted message (a tombstone) still counts. An
   empty DM is reachable only through the picker (R1) or its URL.
6. **Its own section.** The sidebar shows DMs under *Direct messages*, below the channels,
   sorted by the other person's display name, with the same unread badge and bold as a channel.
7. **Named after the other person.** `ChannelResponse` carries the other member's user id on a
   DM, and null on any other kind. The sidebar row, the header, the composer placeholder
   (`Message <display name>`) and a search result all show that person's display name, with no `#`. The
   stored `name` is never shown.
8. **Works like a private channel.** History, send, edit, delete, threads, reactions,
   attachments, typing, read markers, unread counts and search all work in a DM exactly as in a
   private channel. Only a message's author may delete it — a DM has no admin.
9. **Fixed membership.** Rename, topic, archive, add member and remove member are refused for a
   DM. The SPA shows none of those controls, and no member panel, for a DM.
10. **Live arrival.** When a DM gets its first top-level message, `channel_added { channelId }`
    goes to **both** members' personal rooms (`user:{ws}:{userId}`). On it, the SPA refetches
    the channel list. This holds on every first-send path: socket `send_message`, REST
    `POST /channels/{id}/messages`, and an attachment-only message.
11. **Private.** Anyone but the two members gets a 404 for the DM on every REST route and
    socket event, and never sees its messages in search.

## Where the rules meet

- **One per pair and concurrency (R2, R1):** Ada and Grace pick each other at the same instant —
  both land in the same DM; the workspace never holds two for the pair.
- **Listing and delete (R5, R8):** Ada's only message is deleted — the DM stays listed for both,
  showing the tombstone.
- **Listing and unread (R5, R6):** the DM appears for Grace with an unread count of 1; for Ada,
  who wrote it, with none.
- **Two first messages (R10):** Ada and Grace both send into the empty DM at once — each send may
  see itself as first, so `channel_added` may go out twice. At least once is the rule; a
  duplicate is harmless because the client only refetches. No test demands exactly once.
- **The event and a poll in flight (R10):** a 30 s poll that started before the message committed
  must not leave the DM missing — see *Timing*.
- **Naming and the directory (R7):** a user missing from the workspace directory (removed, or not
  loaded yet) shows as `nameFor`'s `shortId` stub, everywhere R7 names them.
- **Delete and no admin (R8, R9):** with no admin row, nobody can delete the other person's
  messages, and the last-admin rule never applies.

## Paths each rule holds on

| Path | What must be true |
|---|---|
| First load | DMs come from `GET /channels`, under *Direct messages*, with unread badges |
| Grace not looking at the DM | its row appears live on `channel_added`; later counts follow the 30 s poll, as for any channel |
| Reconnect after a dropped socket | a missed `channel_added` is recovered by the existing invalidate-on-connect |
| A second tab or device of the sender | gets `channel_added` in its own room and lists the DM |
| Workspace switch | picker and DMs are the current workspace's only; a get-or-create in flight across a switch never puts the old workspace's DM in the new sidebar |
| Open an empty DM, then leave | it stays unlisted for both; picking the same person later returns the same DM |
| A search result in a DM | named after the person, no `#`; opens through the existing `/c/:id?message=` jump |
| A third user with the URL | the same not-found view as a private channel they can't see |

## What this assumes — check before building on it

- **Every non-public kind is member-only** through `_visible_query`'s `kind = 'public' OR member`
  branch, so R8 and R11 need no new visibility rule. R5 does need one: today an empty DM would be
  listed.
- **`_admin_or_403` refuses a caller whose `my_role` is null**, so with no admin row R9's
  refusals may already hold over REST — confirm each route, and the status it answers with.
- **`channels.visible_ids` has no kind filter**, so search includes DMs for their members.
- **TanStack Query 5.101's `invalidateQueries` cancels an in-flight refetch and starts a new one
  — but only when the query already has data** (`query-core` `cancelRefetch`, default true).
  Before the first load completes it reuses the fetch in flight, which may predate the message.
- **A broadcast to `user:{ws}:{userId}` reaches every connection of that user**, since each joins
  its personal room on connect (`realtime.py:225-227`).

## Timing

No throttle or window. The order that matters, for R10:

```
t0  Grace on #general; her 30 s poll fires → GET /channels in flight (no DM in it)
t1  Ada sends "hi" into the empty DM → message committed
t2  channel_added { channelId } → Ada's room and Grace's room
t3  Grace's SPA invalidates the list → the t0 fetch is cancelled, a new GET /channels starts
t4  Grace's sidebar shows Ada's display name under Direct messages, unread 1
    (if t0's response lands before t3, the t3 refetch still replaces it)
```

## Decided already

1. Scope is R1–R11. Everything in *Not in this issue* stays out.
2. DMs are `kind='dm'` channels (D8b); 1:1 only.
3. A DM is listed only once it has a message — the same rule for both members.
4. `channel_added` goes to both members' personal rooms, at least once, carrying only the id.
5. **The `userId` is not checked against Auth.** Like add-member, get-or-create trusts it; the
   picker offers only workspace members, and a DM with a stranger's id is inert because no token
   for this workspace carries that id. Recorded as a gap, not fixed here.
6. This work depends on no 🔴 entry. The nearest: **D18** (notifications) — untouched, the only
   signal is the sidebar; **D28** (preferences) — no per-user state, which is why hiding a DM is
   out.

Left to the plan, on purpose: how the pair is keyed and made unique, the route shape and its
status codes (200 vs 201), what goes in the unused `name`, the DTO field's name, how R9's
refusals answer, and the picker's UI.

## Tests

- **pytest and Vitest below the journey:** pair uniqueness, including a concurrent open; no
  self-DM; the listing rule with an empty, a live and a tombstoned DM; the other member's id on
  the DTO; a 404 for a third user over REST and the socket; every management route refused for a
  DM; author-only delete; `channel_added` on each first-send path, to both rooms and to no one
  else; DM search results reaching members only; the SPA's section, sort, naming and hidden
  controls.
- **One BDD journey:** Ada starts a DM with Grace from the sidebar's **+** and sends "hi"; Grace,
  already on #general, sees Ada's display name appear under *Direct messages* with an unread badge without
  reloading, opens it and replies; Ada sees the reply live.

## Record in this slice

- Register: **D8b → 🟢**; a new entry for the unchecked `userId` on get-or-create and add-member.
- Doc 02: the route, the DTO field, `channel_added`, the listing rule, the pair constraint.
- Doc 06: the *Direct messages* section, the picker, naming after the other person.
- An ADR: DMs as `kind='dm'` channels, one per pair, listed on first message, `channel_added`.

## Not in this issue

- Group DMs, and a DM with yourself.
- A "Message" button on a member in the member panel.
- Ordering DMs by recent activity.
- Hiding or closing a DM.
- Checking the other user's workspace membership with Auth.
- Anything on removal from the workspace: the DM and its history stay, and the person shows as
  the `shortId` stub.
- Notifications beyond the sidebar (D18).

## Acceptance — first real run on Compose

With Ada, Grace and Alan in three browsers:
- Ada opens a DM with Grace and leaves without typing: neither sidebar lists it.
- Ada sends "hi": Grace, on #general, sees Ada's name under *Direct messages* with a badge at once;
  Ada's second tab lists it too.
- Grace picks Ada from her own **+**: she lands in the same DM, with "hi" in it.
- Alan opens the DM's URL: not found. Alan searches "hi": no result.
- The DM's header shows Grace's display name for Ada and Ada's for Grace, with no rename, archive or members.

## References

- `docs/design/02-messaging-service.md` §3.1, §3.2, §4
- `docs/design/06-frontend-spa.md` §3, §5.2, §5.4
- `docs/design/07-open-decisions-register.md` D8b, D18, D28, D31
- `docs/adr/261002-unread-state-polls-rather-than-pushes.md`
- Commit `c2ca4e3` (threads) — template for a new broadcast and its cache writer
