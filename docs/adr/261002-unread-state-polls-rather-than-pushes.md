# Unread state in the SPA polls rather than pushes

- **Status:** Accepted
- **Date:** 2026-10-02

## Context

The sidebar now shows each channel's unread count. The server already computes it
(`unreadCount` on the channel list, register D31) and already tells a user's other
tabs when a marker moves (`read_receipt_updated`, to the user's own room). What it
does **not** send is a signal that *another* user posted in a channel the viewer is
not looking at: `message_received` goes to the channel's room, and the SPA is only
in the room of the channel it has open.

So the badge of a background channel can learn of a new message only by asking.
Any push would be a backend change, and this slice changes none: no event, no
chart, no environment variable.

## Decision

The channel list **polls**. `useChannels` refetches every 30 seconds while the tab
is visible (TanStack skips the tick while it is hidden), and the SPA also refetches
it when the window regains focus or the tab becomes visible, on every socket
connect, and on every channel switch. A user's own receipts from another tab are
applied from `read_receipt_updated`.

A background channel's count can therefore be up to 30 seconds behind. That is the
accepted cost: the count is a hint that something is waiting, and the channel
itself, once opened, is live.

## Consequences

- No backend change, so the SPA ships alone and nothing depends on a new event.
- One extra `GET /channels` every 30 seconds per visible tab. The list query walks
  the marker forward per channel (see the read-state ADR); a workspace with many
  channels and many open tabs pays for it.
- The lag is visible in a two-user demo: a message in another channel shows its
  badge after the next poll, not at once.
- **Revisit** when the 30-second lag or the list query's load becomes a problem.
  The fix is a push to the user room — Messaging emitting a `channel_activity`
  event there on each message — which turns the poll into a fallback.

## Alternatives Considered

### A `channel_activity` event to the user room

The server tells each member's room that a channel they can see has a new message.
Counts would be immediate and polling unnecessary. Rejected for now: it is a new
event contract in Messaging, a fan-out on every message to every member of a
channel, and a decision on what the payload carries — all to remove a lag nobody
has yet complained about. It is the planned way out, not a rejected idea.

### Joining every visible channel's room

The SPA would join each channel it can see and count `message_received` itself.
Rejected: it makes the client compute an unread count the server already owns (two
implementations of the rule, D24), and one connection in hundreds of rooms costs
the server far more than one poll does.

### Refetching on focus only

No interval, just the focus and visibility refetch. Rejected: a tab left open and
in front — the common case for a chat window — would never refresh, and the badge
would be wrong exactly where people look at it.
