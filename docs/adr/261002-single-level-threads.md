# Single-level threads, kept out of channel history, unread and search

- **Status:** Accepted
- **Date:** 2026-10-02

## Context

Register D8a left threading depth open with a working default of single-level. The
`messages.thread_root_id` column had shipped ahead of any API, always `null`. Issue 3
builds the feature: anyone who can see a channel can reply to a message, the replies sit
in a panel beside the channel, and each root shows its reply count and last-reply time,
live for everyone in the channel's room.

The design has to decide where a reply is *not*. If replies appear in channel history they
push the conversation out of view, which is the problem threads exist to solve. If they
count as unread, a busy thread makes every channel look unread, and there is no thread
read state to clear it (D18, notifications, is open). If they are searchable, a result
opens a message the SPA has no way to show in context.

## Decision

Threads are single-level. A `threadRootId` naming a reply is filed under that reply's
root. A reply is a `messages` row with `thread_root_id` set, and one predicate
(`thread_root_id IS NULL`) keeps it out of history, the unread count and search
hydration. `mark_read` naming a reply is refused as a message not in the channel.
Replies stay in the Elasticsearch index, so no reindex is needed and replies become
searchable by dropping one predicate.

A root's `replyCount` and `lastReplyAt` are aggregated per page in one grouped query over
a new partial index (`ix_messages_thread`), the pattern reactions already use, and ride
on every `Message` built from a stored row. They are broadcast as an idempotent set in
`thread_summary_changed`, read after the reply's commit so the last writer to commit
counts everyone before it. A deleted root keeps its thread and its summary.

The SPA keeps each thread in its own infinite query nested under the channel's history
key, routes every message event by `threadRootId`, and renders the panel from
`?thread=<rootId>` in place of the member panel.

## Consequences

Replies cost the channel nothing: history, unread and search behave as before. Counts are
always derived, so deleting a reply needs no counter repair, at the price of one grouped
query per page of history and search results.

Two replies committed within milliseconds on two pods can leave a count one low in every
window until the next refetch, because the broadcasts may arrive out of order (the same
window `reaction_changed` has). A per-root sequence on the event would close it.

Replies are not searchable and not unread, so a reply nobody opens is invisible outside
its thread. That is deliberate for this slice, and each half is one predicate to reverse.
Edits and deletes of a message nobody loaded into history no longer insert it as the
newest message (history takes a new row only from `message_received`).

## Alternatives Considered

### Also send the reply to the channel

Duplicates the message in two places and needs two identities for one row. It also defeats
the purpose of keeping the channel readable. Left out of scope.

### Count replies as unread

Needs a thread-level read marker and a notification story (D18) before it means anything.
Without them the channel badge cannot be cleared by reading the channel.

### Make replies searchable now

A hit would need to open a thread to a specific reply, which the panel does not support.
The index already holds replies, so adding it later needs no reindex.

### Stored `reply_count` / `last_reply_at` columns on the root

Two writers to keep in step, and `last_reply_at` must be recomputed on every reply delete
anyway.
