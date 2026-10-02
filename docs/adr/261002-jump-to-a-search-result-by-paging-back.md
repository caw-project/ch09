# Jump to a search result by paging history back on the client

- **Status:** Accepted
- **Date:** 2026-10-02

## Context

A search result names a message in a channel. Opening it should land the reader on that
message, in the middle of the conversation around it. Messaging serves history newest-first
by cursor and offers no way to ask for "the page around message X". The SPA's history is a
TanStack infinite query that only ever grows towards older messages, and it is refetched
whole by the mount refetch and by the join-ack refetch after a reconnect.

Two things make a client-side seek delicate: TanStack's default is that a page fetch
cancels a refetch in flight (and a refetch cancels a page fetch), and a read mark must not be
sent while the reader is being taken somewhere else.

## Decision

We will page history back on the client. A result links to `/c/:channelId?message=<id>`;
`MessageList` runs a jump that decides only while history is idle, fetches the next older page
when the target is not loaded, and stops at ten loaded pages in total (pages already cached
count). On finding the target it centres and highlights it for two seconds, then removes the
parameter. At the cap it shows the newest messages with a notice. Reads and auto-scroll are
held off for the jump's duration.

To make that safe, no page fetch cancels a refetch (`cancelRefetch: false`) and the join-ack
refetch goes through `refetchHistory`, which waits for a page fetch in flight rather than
cancelling it. No Messaging change is needed.

## Consequences

A result up to ten pages back opens in place with no server work, and the cache stays one
ordered list. A result further back than ten pages shows the newest messages and a notice
instead of its target. The jump costs up to ten sequential requests, and the fetch rules
above are now a constraint on every future caller of history: a page fetch must not cancel a
refetch. The mount-time refetch of an infinite query re-fetches every loaded page, so a
long-cached channel pays for its pages again.

Revisit when the cap is hit often: that is the signal to add an `around` parameter to history.

## Alternatives Considered

### An `around=<messageId>` parameter on history

The server would return the window around the message. It is the right answer for deep
results, but it changes a published endpoint, needs a second cursor direction, and the SPA
would need a two-way cache (pages that grow newer as well as older). Too large for this slice;
the paging approach does not prevent it later.

### Opening the channel at the bottom and leaving the reader to scroll

Cheap, and wrong: the point of search is to find one message, and "scroll up and look" defeats it.
