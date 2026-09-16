# Message reactions are counted server-side and delivered as facts, not documents

- **Status:** Accepted
- **Date:** 2026-09-16

## Context

Doc 02 named reactions in three places — the endpoint table, the `Message` DTO and
the DDL — and nothing implemented them. Unusually for this project the feature had
**no row in the open decisions register at all**: not 🟢, not 🔴, simply absent. So
building it meant deciding it.

Three forces shaped the design, and they turned out to be one problem rather than
three.

The first is **write frequency**. A reaction is the cheapest thing a person can do
in a chat app, so it is the most frequent write in the system, and it arrives in
bursts — six people hitting the same emoji on the same message within a second.
Whatever mechanism carries it is exercised far harder than sending a message.

The second is that **"have I reacted?" is a per-caller question**. The count on a
chip belongs to the channel; whether the chip is lit belongs to one person. Every
other field on the `Message` DTO is the same for everyone who can read it.

The third is **the shape of the client**. The SPA keeps server state in a TanStack
Query cache and applies socket events into it with `upsertMessage`, which replaces
a cached message wholesale and has no version guard. That helper is correct for
the events it serves today, and it is a loaded gun pointed at any high-frequency
event that carries a whole document.

## Decision

We will model a reaction as a row in `message_reactions` keyed on
`(message_id, user_id, emoji)`, write it over REST only, aggregate it onto the
`Message` DTO, and broadcast changes as a small fact rather than a document. The
four parts hold each other up, which is why they are recorded together rather
than as four ADRs.

**The composite primary key is the concurrency control.** Adding a reaction is
`INSERT … ON CONFLICT DO NOTHING`; removing one is a plain `DELETE`. A
double-click, a retried request and two tabs racing each other all converge on
the same state. There is therefore no `version` column — there is nothing to
conflict on — and no `deleted_at`, because removing a reaction is a real delete
with no history to preserve. This is the same argument D31 made for the
forward-only read marker.

**Writes are REST, deliveries are socket.** The socket write handlers that exist
(`send_message`, `edit_message`) earn their place by needing ack-and-reconcile
against an optimistic `temp:` id. A toggle has no such problem: the client knows
what it clicked. So reactions add no inbound socket surface, and doc 02's
`add_reaction` / `remove_reaction` events are recorded as not built.

**Counts are aggregated onto the `Message` DTO** as `{emoji, count, reacted}`,
built by one grouped query over a whole page of message ids rather than one query
per message. A separate `GET /messages/{id}/reactions` would mean fifty fetches
for a fifty-message page, or a batch endpoint invented to avoid them.

**The broadcast carries the authoritative count, plus the actor's own state:**
`{messageId, channelId, emoji, count, userId, reacted}`. Not a delta, and not a
`Message`.

## Consequences

Idempotency stops being something the application maintains and becomes something
the schema guarantees. No read-then-write, no advisory lock, no retry logic — and
the integration test that double-posts a reaction and expects a count of one is
asserting a property of the primary key, not of a code path.

The client's merge becomes an idempotent *set* rather than a delta application,
which matters more than it sounds. The person who clicks applies their own change
up to three times: optimistically, from the REST response, and from their own echo
of the broadcast. A `+1` would treble it, and skipping the actor's own socket does
not fix it — a REST write has no `sid` to skip, and their other tabs still need the
event. Carrying the count makes all three applications agree. It also makes the
first optimistic REST mutation in the SPA safe to write, since rollback is a
snapshot restore rather than an inverse.

The cost is that the `Message` DTO is now **caller-dependent**: the same message
serialises differently for two people, because `reacted` is computed per request.
That forecloses ever caching a page of messages and sharing it between users, and
it is why `reaction_changed` cannot reuse the existing `_publish` helper — one room
emit delivers one payload, so broadcasting the DTO would light the actor's chip in
everyone's window. The SPA therefore needs a second handler and its own cache
writer, roughly 150 lines that a document-shaped event would not have needed.
`ChannelResponse` was already caller-dependent (`myRole`, `unreadCount`), so this
extends an existing property rather than introducing one.

We also accept a small, real cost on every history read: one extra grouped query
per page. An integration test asserts it is exactly one, because an N+1 here would
change nothing about the response and so would never be noticed.

Reactions are counts only. Nobody can see *who* reacted, which is a feature people
will ask for and which cannot be added without deciding how much a reaction
discloses and capping an unbounded list of ids.

## Alternatives Considered

### Broadcasting the whole `Message`, as `message_deleted` does

By far the cheapest option in code: the SPA's existing `onMessage` handler would
absorb `reaction_changed` with no new handler, no cache writer, and no idempotency
concern, since `upsertMessage` already replaces by id.

It is wrong three times over. `reacted` is per-caller and a room emit sends one
payload, so every recipient would receive the actor's lit state. It would put the
message body back on the wire on every click, to people who already have it. And
because `upsertMessage` replaces a message wholesale with no version check, a
reaction event built before a concurrent edit would silently revert that edit in
every client — the high-frequency write clobbering the one that matters.

### A delta payload (`action: "added" | "removed"`)

The conventional shape, and smaller than a count. It requires exactly-once
application, which is precisely what this system cannot promise: three code paths
apply the actor's own change, and the event may be re-applied when an in-flight
history fetch lands. An authoritative count is idempotent under all of it.

### Shipping user ids instead of a `reacted` flag

`{emoji, count, userIds}` would make the DTO caller-independent — cacheable,
shareable, and broadcastable as a whole document — and would give "who reacted"
away for free.

It decides a privacy question nobody has asked, and the payload has no bound: six
emoji times *n* reactors times fifty messages a page. A 500-person channel where
300 people agree is 300 UUIDs on one chip. Capping the list means building the
separate endpoint the aggregate was meant to avoid, and paying for both.

### Free unicode emoji rather than a fixed allowlist

More expressive, and what people expect from a mature chat product. It brings NFC
normalisation, grapheme segmentation, skin-tone and ZWJ sequences, a variable-width
value in an indexed column, and a moderation surface. A six-shortcode allowlist
makes validation a pure function over a constant — testable at the lowest layer of
the pyramid — and is trivial to widen later. Narrowing it would strand rows, so it
starts small.

### Writing reactions over the Socket.IO namespace

Consistent with how messages are sent, and it would keep every message mutation on
one transport. But it puts reactions outside the OpenAPI document the SPA's types
are generated from, makes them unreachable to any non-socket caller, and is harder
to drive from an integration test — all to avoid a REST call that needs no
reconciliation.
