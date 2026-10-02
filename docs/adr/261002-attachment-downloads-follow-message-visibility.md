# Attachment downloads follow message visibility, and a send claims its files first

- **Status:** Accepted
- **Date:** 2026-10-02

## Context

File attachments (issue 4) are the first feature that moves bytes. The design gave Asset a
public `GET /assets/{id}/download-url` for a "viewer", but an asset has no viewers of its own:
an attachment is visible to whoever can see the *message* it is on, and that is a fact only
Messaging holds (channel visibility, private channels, archived channels). Asset cannot answer
it without reading Messaging's data, which Conventions §2 forbids. Two further problems shared
the same root: a message must not exist with files that turn out to be someone else's, still
uploading or already on another message, and a user must not be able to attach the same
uploaded file to two messages and so read it through either.

## Decision

Messaging authorizes every download. Asset has no public download route; a client asks
Messaging for `GET /messages/{messageId}/attachments/{assetId}/download-url`, which applies the
channel-visibility rule and its own record of what is on the message (a deleted message and an
asset not on the message are 404 without a call to Asset), then calls Asset's internal
`download-url` with a service token scoped `assets:download`.

A send **claims first**. Messaging chooses the message id, claims the assets from Asset
(`assets:claim`) for that id — all or none, under a row lock — and only then inserts the message
and a metadata snapshot in `message_attachments`. A refused or unreachable claim leaves nothing
behind and is a 409 or 503. Asset records the claim in `assets.message_id`; a download URL is
minted only for the message that holds it. A message with no attachments makes no call.

## Consequences

Visibility has one implementation, so a file can never be more visible than its message. The
cost is a second hop on every download, and a coupling in the other direction: a send now
depends on Asset (and Auth, for the service token) being reachable *when it carries files*.
That is why Asset is not a readiness check for Messaging, and why the 503 says nothing was sent.

A claim that succeeds followed by an insert that fails strands the asset on a message that
never existed, and a lost ack followed by a retry is refused `already-attached` because the
first send did claim the files — the SPA's timeout wording says the message "may still arrive".
Neither unsent `pending` assets nor the blobs of deleted messages are ever swept (register D16,
still open), so storage grows.

The snapshot means a page of history needs no call to Asset and a chip cannot change under a
message, at the price of a second copy of name, type and size.

## Alternatives Considered

### Asset authorizes downloads

It would need Messaging's channel rules, either by reading its tables (forbidden) or by calling
back for every download, which is the same hop with the dependency pointing both ways.

### A claims table in Asset, or a message-side jsonb column

A separate claims table is one more join for nothing; a jsonb column on `messages` adds writes to
the hottest table and loses the uniqueness that refuses a repeated asset.

### Insert the message, then claim

A failed claim would leave a message with files that are not there, and the fix is a compensating
delete of something already broadcast. Claiming first makes failure free.
