# CollabHub — Messaging Service

> Channels, threads, messages, reactions, read receipts, and real-time delivery.
> Read [Platform Conventions](./00-platform-conventions.md) first.

**Status:** Draft · **Runtime:** Python 3.12 / FastAPI + Socket.IO
**Owns:** channels, membership, messages, threads, reactions, read receipts
**Depends on:** PostgreSQL (own DB), Redis Real-time (R2), Redis Cache (R1), Redis Streams (R3)

---

## 1. Purpose & Responsibilities

The chat half of CollabHub. Provides Slack-like channels and threaded messaging with
sub-second real-time delivery.

**Owns:** channels and their membership/permissions, messages, threads, reactions,
read receipts, typing indicators.
**Produces:** index jobs to `jobs:index` (R3) for Elasticsearch (consumed by Worker) — built
2026-09-14, see §5.
**Does NOT own:** the search index (the Worker owns its mapping and writes; this service only
queries it through `GET /search/messages` — see §3.1.6), file blobs (Asset Service owns them).
Messaging keeps a **metadata snapshot** of each attachment — name, type, size — in
`message_attachments` (§4), and it **authorizes every download** (§3.1.4, register D43).
**Calls:** Asset's internal API with its own service token (`assets:claim`, `assets:download`),
to claim a send's files before the message exists and to mint download URLs.

---

## 2. Runtime & Dependencies
- FastAPI REST + a Socket.IO server on the `/messaging` namespace, with the R2 backplane
  (Conventions §6). The Socket.IO ASGI app is mounted alongside FastAPI on one Uvicorn process.
- SQLAlchemy 2.0 (async) + asyncpg; Alembic migrations.
- `redis-py` (`redis.asyncio`) for R1 (hot data), R2 (Socket.IO Redis manager / pub-sub),
  R3 (index jobs).

---

## 3. Public Interface

### 3.1 REST (`/api/v1`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/channels` | member | List channels visible to the user (cursor paginated, alphabetical). |
| POST | `/channels` | member | Create channel. Creator becomes its admin. |
| GET | `/channels/{id}` | see §3.1.1 | Channel detail. |
| PATCH | `/channels/{id}` | see §3.1.1 | Rename / change topic. Takes `name`, `topic` and a required `version`; **never** `archivedAt`. |
| DELETE | `/channels/{id}` | see §3.1.1 | Archive. Unconditional, no body, **one-way** — see §3.1.1. Returns the archived channel. |
| GET | `/channels/{id}/members` | see §3.1.1 | List members. Ordered by `userId` and keyset-paginated on it. |
| POST | `/channels/{id}/members` | see §3.1.1 | Add **one** member, by id. Already a member → 409. |
| DELETE | `/channels/{id}/members/{userId}` | see §3.1.1 | Remove member. Not a member → 404; the channel's only admin → 409. |
| GET | `/channels/{id}/messages` | see §3.1.1 | History, cursor paginated, newest-first. Includes tombstones. |
| POST | `/channels/{id}/messages` | see §3.1.1 | Send message (REST fallback; prefer the Socket.IO event). |
| GET | `/messages/{id}` | see §3.1.1 | Single message, with its reply summary. |
| PATCH | `/messages/{id}` | author only — see §3.1.4 | Edit message. Takes `body` and a required `version`. No time window. |
| DELETE | `/messages/{id}` | author or channel admin — see §3.1.4 | Tombstone the message. Returns **200 with the tombstoned `Message`**, not 204. |
| GET | `/messages/{id}/thread` | see §3.1.1 | A root and a cursor page of its replies, newest first, tombstones included (`ThreadResponse`). A reply's id → 404 "No such thread."; unknown or invisible → 404 "No such channel." Built 2026-10-02 (D8a). |
| GET | `/messages/{id}/attachments/{assetId}/download-url` | see §3.1.1 | A 15-minute URL for one attachment, for anyone who can see the message. **The only way to a file's bytes** (register D43) — see §3.1.4. Returns `{url, expiresAt}`. |
| POST | `/messages/{id}/reactions` | see §3.1.1 | Add a reaction `{ "emoji": "thumbsup" }` — a shortcode from the server's allowlist, not a character. Idempotent. Returns **200 with the updated `Message`**. See §3.1.5. |
| DELETE | `/messages/{id}/reactions/{emoji}` | see §3.1.1 | Remove your own reaction. Idempotent — removing one that was never there is also a 200 with the `Message`. |
| POST | `/channels/{id}/read` | see §3.1.7 | Mark read up to `{ "messageId": "..." }`. 204; the marker only moves forward. |
| GET | `/search/messages?q=` | any workspace member — see §3.1.6 | Thin proxy to Elasticsearch (D8c). Newest first, only channels the caller can see. |

**Internal** (`/api/v1/internal/`, service token only — Conventions §5.5; never reachable
from the public ingress, and never carrying `require_user`):

| Method | Path | Scope | Purpose |
|--------|------|-------|---------|
| POST | `/internal/messages/sweep` | `messages:retention` | Delete messages past the retention window. The Worker calls this; it deletes nothing itself (register D25). |

**Every channel is scoped to the workspace in the token's `wsp` claim.** `channels.workspace_id`
comes from the claim and never from the request body or a query parameter — Conventions §5.4
is explicit that authorization must not accept a workspace identifier in place of the claim,
and substituting one here is a tenancy leak. A caller who wants another workspace switches
token first (`POST /auth/switch-workspace`).

Channel membership is *not* workspace membership, so these writes are **not** in the
fail-closed denylist set (Conventions §5.2) — that set names workspace membership changes,
role grants and asset deletion.

List endpoints use the cursor pagination in `collabhub-shared` (`?limit=`/`?cursor=`,
`{items, nextCursor}` — Conventions §4.1). Never `OFFSET`.

#### 3.1.1 Channel visibility

**Corrected 2026-08-15, while building the channels slice.** This table
originally marked channel detail "channel member", and never defined the list
rule at all. Together those made a public channel unopenable by anyone but its
creator — you could see `#general` in the sidebar and get a 403 clicking it,
until an admin added you. That is not what a public channel means.

| Request | Result |
|---|---|
| `GET /channels` | non-archived `public` channels in the token's `wsp`, **plus** any kind the caller is a member of |
| `GET /channels/{id}`, public, same workspace | 200 — membership is **not** required |
| `GET /channels/{id}`, private, member | 200 |
| `GET /channels/{id}`, private, non-member | **404** |
| `GET /channels/{id}`, any other workspace | **404** |

Membership gates the *messages* in a channel, not the knowledge that it exists.

A caller who may not see a channel gets **404, never 403**. A 403 confirms the
channel exists and discloses its name to someone with no access to it; from that
token's point of view it does not exist, and the response says so.

Channels sort by `(name, id)`. The pair is the cursor: `name` alone is not
unique, because private channels and DMs may repeat one.

**Added 2026-08-16, while building channel administration.** Visibility answers
who may *see* a channel; it did not answer who may *change* one. Two guards, in
this order, on `PATCH`/`DELETE /channels/{id}` and on every `/members` write:

| Caller | Result |
|---|---|
| the channel is not visible (other workspace, archived, private non-member, absent) | **404** `not-found` |
| visible, `myRole` is `null` or `member` | **403** `forbidden` |
| visible, `myRole == "admin"` | proceed |

The order matters more than either rule. Visibility decides the 404 and only
then does the role decide the 403, so a private channel is always "absent"
before it can be "not yours". The 403 that survives is safe on its own terms: it
is reachable only for a channel the caller can already read, where "you are not
an admin of it" discloses nothing new.

**Reading the member list is a visibility test, not a membership test.** This
table marked it "channel member", and applied literally that let Grace see
`#general` in her sidebar, read every word in it, and get a 403 for asking who
else was in it. It widens exactly one case — a public channel, where the
membership is not a secret from a workspace that can already read the
conversation.

**Archiving is one-way.** Every read in the service goes through the visibility
query, which filters `archived_at IS NULL`, so an archived channel is invisible
to everyone including its own admin: there is no `GET /channels?archived=true`,
no restore route, and archiving twice is a 404. Adding either would mean a read
path that sees archived rows. Two consequences worth stating rather than
discovering: the SPA confirms before archiving and navigates away afterwards,
and **the name is not released** — `ux_channels_public_name` covers archived
rows too, so `#general` cannot be created again once it has been archived.

**Nothing joins a channel by itself.** Both member writes require a channel
admin, including when the target is the caller: there is no self-join and no
self-leave in this scope.

**Added 2026-08-16, while building messages. Visibility gates reading *and*
writing; membership gates administration.** This table marked the message rows
"channel member", and read with the two facts above — a public channel is
visible to the whole workspace, and nobody can join a channel by themselves —
that recreates exactly the bug §3.1.1 was added to fix. Ada creates `#general`,
Grace sees it in her sidebar, and can never read a word in it.

| Request | Rule |
|---|---|
| `GET /channels/{id}/messages` | the caller can see the channel |
| `POST /channels/{id}/messages` | the same test. Posting in a public workspace channel needs no membership row |
| `GET /messages/{id}` | the same test, applied to the message's channel |
| a channel the caller cannot see | **404**, and the *message* 404 uses the same wording, so an id cannot be probed |
| an archived channel | unreachable by the same code path, deliberately |

**Posting does not create a membership row.** `myRole` stays `null` for someone
who has spoken in a public channel they never joined, and the admin controls
stay hidden. Whether posting *should* join you is a product question, not
something to settle by accident in a handler.

#### 3.1.2 Channel names

**Added 2026-08-15.** The docs previously gave no format at all, and one length
in a Conventions §4.2 *example* ("between 1 and 80 characters"). The rule:

- 3 to 80 characters, after trimming
- letters, numbers and hyphens only — ASCII `[A-Za-z0-9-]`
- must start with a letter
- unique among the **public** channels in a workspace, compared **without case**:
  `#General` collides with `#general`. The name is stored and displayed exactly
  as typed; only the index folds case
- a duplicate is `409 conflict`; a broken format rule is `400 validation-error`
  with the reason under `errors.name`, one message per rule so a form can show
  which part was wrong

This is a real narrowing: `#café` is not a valid channel name, and neither is
any name in a non-Latin script. Worth revisiting before a customer outside
English-speaking markets.

`kind` accepts `public` and `private` on `POST /channels`. A `dm` is opened
through `POST /channels/dm` instead (**added 2026-10-05**, register D8b): a DM has
no name to give and no creator-as-admin, and creating one by name would skip the
pair key.

**Direct messages (added 2026-10-05).** `POST /channels/dm {"userId"}` gets or
creates the one DM between the caller and `userId` in the caller's workspace, and
answers **200** either way. A DM's stored `name` is the pair key `dm:{low}:{high}`
(the two ids sorted), unique per workspace through `ux_channels_dm_pair`, so two
people opening at once get one channel. Both people are `member`; nobody is
`admin`. Any workspace role may open one; the id is not checked against Auth
(register D44). A DM with yourself is `400`, `errors.userId`.

- **Listing.** `GET /channels` returns a DM only once it has a top-level message
  (a tombstone counts), for both people. An empty DM is still reachable by id.
- **Refusals.** Rename, topic, archive and both member writes on a DM are `403`
  "A direct message can't be renamed, archived or have its members changed.",
  after the 404 and before the admin check. Only the author deletes a message.
- **Everything else** is a private channel's behaviour. A third person gets `404`
  on every route and socket event.
- **`dmPartnerId`** on the Channel DTO is the other person, per caller; `null`
  on any other kind.

#### 3.1.3 DTOs

`Channel` DTO — **added 2026-08-15**; the doc previously specified only
`Message`:

```json
{
  "id": "uuid", "name": "general", "topic": "string|null",
  "kind": "public|private|dm", "createdBy": "uuid",
  "createdAt": "...", "updatedAt": "...", "archivedAt": "...|null",
  "version": 0,
  "lastReadId": "uuid|null", "unreadCount": 0,
  "dmPartnerId": "uuid|null",
  "myRole": "admin|member|null"
}
```

`dmPartnerId` — **added 2026-10-05** — is always present: the other person in a
direct message, computed per caller from the pair key, `null` on any other kind.

`lastReadId` and `unreadCount` — **added 2026-09-15** — are the caller's read
state (§3.1.7). Both are always present and neither is optional in the OpenAPI
document, so the generated type does not make every sidebar render null-check a
count the server always sends. A channel just created reports `null` and `0`.

There is deliberately no `workspaceId`: a channel is always in the workspace
named by the caller's `wsp` claim, and echoing it invites a client to start
sending it. `myRole` is the caller's role in that channel, `null` if they are
not a member — it is what decides whether the UI offers the admin controls.

Membership DTOs — **added 2026-08-16**; `POST /channels/{id}/members` had no
request or response body specified at all:

```jsonc
// AddChannelMemberRequest
{ "userId": "uuid", "role": "member" }   // role optional, "member" | "admin", default "member"

// ChannelMember
{ "userId": "uuid", "role": "admin|member", "joinedAt": "..." }

// ChannelMemberListResponse
{ "items": [ /* ChannelMember */ ], "nextCursor": "…|null" }
```

Three things follow from Conventions §2 — **Messaging owns no user records and
must not read Auth's tables**:

- **By id, never by email.** Messaging cannot resolve an address, and it will
  not make a synchronous call to Auth on the path of a channel edit.
- **`userId` is not validated against anything.** A membership row for an id
  that is not a user in this workspace grants nothing — every read still filters
  on the caller's own `wsp` claim, so the row is inert.
- **There is no name here to give.** The SPA resolves ids to display names
  through Auth's own `GET /workspaces/{id}/members`, holding a token that
  already entitles it to both services. Copying a name onto Messaging's rows
  would put a fact Auth owns into Messaging's database, and would go stale the
  moment someone renamed themselves.

Nothing is revoked when a member is removed: channel membership is in no token,
which is the same fact that keeps these routes on plain `require_user`. Contrast
Auth's workspace removal, which must revoke sessions — there is no equivalent
here to write.

`UpdateChannelRequest` carries `version`, `name` and `topic`. An absent `topic`
leaves it alone; an explicit `null` clears it.

`Message` DTO — **replaced 2026-08-16.** The previous shape carried `reactions`
and no `version`, and neither was right for what the service actually is:

```jsonc
{
  "id": "uuid", "channelId": "uuid", "authorId": "uuid",
  "threadRootId": "uuid|null",     // set on a reply; null on a top-level message (D8a 🟢)
  "body": "markdown text",         // "" when deletedAt is set — see §3.1.4
  "attachments": [                 // [] when none; in the order attached; always [] when
    {                              // deletedAt is set — see §3.1.4. Built 2026-10 (issue 4)
      "assetId": "uuid", "fileName": "diagram.png",
      "contentType": "image/png", "sizeBytes": 1234
    }
  ],
  "reactions": [                   // [] when nobody has reacted — see §3.1.5
    { "emoji": "thumbsup", "count": 3, "reacted": true }
  ],
  "createdAt": "...", "editedAt": "...|null", "deletedAt": "...|null",
  "version": 0,
  "replyCount": 0, "lastReplyAt": "...|null"   // a root's live replies — added 2026-10-02
}
```

- **`replyCount` and `lastReplyAt` — added 2026-10-02** (D8a). The count of a
  root's non-deleted replies and the newest one's `createdAt`, aggregated per page
  in one grouped query over `ix_messages_thread`. `0`/`null` on a reply and on a
  message nobody answered; a deleted root keeps its summary. Required, no default.
- **`reactions` is a summary — added 2026-09-16** (register D39). One entry per
  emoji anyone used, carrying the count and whether **the caller** is one of
  them, built by a single grouped query over a whole page of messages rather
  than one query per message. `[]` when nobody has reacted, never absent.
  Counts only, no user ids: a "who reacted" list is a privacy decision nobody
  has made. Because `reacted` is computed per request, this DTO is
  caller-dependent — which is why `reaction_changed` cannot carry a `Message`
  (§3.2).
- **No `workspaceId`**, for the reason the `Channel` DTO gives.
- **`version` is here**, because a `PATCH` sends it back for optimistic
  concurrency (§4).
- **`authorId` is a bare id.** There is no user expansion — Messaging does not
  read Auth's tables — and the browser resolves the name through Auth's own
  workspace directory.

```jsonc
// MessageListResponse — matches ChannelListResponse
{ "items": [ /* Message */ ], "nextCursor": "…|null" }

// SendMessageRequest — POST /channels/{id}/messages
{ "body": "markdown text", "threadRootId": "uuid|null", "attachmentIds": ["uuid"] }   // both optional; attachmentIds default []

// ThreadResponse — GET /messages/{id}/thread
{ "root": { /* Message */ }, "items": [ /* replies, newest first */ ], "nextCursor": "…|null" }
```

`SendMessageRequest` carries **no** `channelId` (it is in the path) and no
`authorId` (it is the token's `sub`). `threadRootId`
(added 2026-10-02) makes the message a reply; one naming a reply is filed under
that reply's root, and one that is unknown or in another channel is a 404 "No
such thread." (never a 403).

**Attachments — built 2026-10 (issue 4).** `attachmentIds` are assets the caller has
uploaded and confirmed with Asset, in the order they should appear.

- **At most `MESSAGING_MAX_ATTACHMENTS` (10), and no id twice** — 400 with the message under
  `errors.attachmentIds` ("A message can have at most 10 attachments." / "An attachment is
  listed twice."). A repeat is refused rather than silently de-duplicated, which would make
  the order ambiguous.
- **The body may be empty only when there is at least one attachment.** `""` alone is still
  "A message cannot be empty."; a whitespace-only body with attachments is stored as `""`.
- **Claim, then insert.** Everything refusable is refused first (visibility, count, body),
  then the message's id is chosen (UUID v7, in the application), the assets are **claimed from
  Asset for that id** — all or none — and only then are the message and its
  `message_attachments` rows written, committed, then published. A refusal or an unreachable
  Asset therefore leaves **nothing** behind. The body is validated *before* the claim, so a bad
  body never claims files for a message that will not exist.
- **A refused claim is 409** with `detail` for the first refused asset *in attach order*:
  "An attachment could not be found." · "An attachment was uploaded by someone else." · "An
  attachment has not finished uploading." · "An attachment is already on another message."
  **Asset unreachable, or no service token obtainable, is 503** "Attachments can't be checked
  right now. Nothing was sent."
- **A retry after a lost ack is `already-attached`**, because the first send did claim the
  files and was saved. The SPA's wording for a timeout says the message "may still arrive".
- A send with no attachments **makes no call to Asset**.
- The service token is cached until 60 s before it expires, one fetch in flight at a time, and
  dropped and refetched once if Asset answers 401 (`shared.ServiceTokenSource`).

**Message body rules — added 2026-08-16.** §8 gave one number and no floor, no
layer and no error key:

- **Empty, or nothing but whitespace, is rejected** — 400 `validation-error`,
  `errors: {"body": ["A message cannot be empty."]}`. Emptiness is judged on the
  *stripped* string.
- **The body is stored verbatim and is not trimmed**, unlike a channel name.
  Markdown is whitespace-sensitive: an indented code block and a hard line break
  both mean something.
- **Length is `MESSAGING_MAX_BODY_CHARS` characters of the raw string**, checked
  in the domain so the message can name the limit —
  `errors: {"body": ["A message must be 8000 characters or fewer."]}`.
- The request model also carries a static `max_length` far above the configured
  limit. It exists only to keep an unbounded body out of the domain, and it must
  stay above the setting — otherwise raising `MESSAGING_MAX_BODY_CHARS` would
  silently start reporting a generic error from the wrong layer.

#### 3.1.4 Editing and deleting a message

**Added 2026-08-16.** Register **D8d** is settled — see the
[ADR](../adr/260816-message-edit-and-delete-semantics.md). The doc gave the Auth
column for these two routes and nothing else: no request body, no response, no
statement of what a refusal looks like, and no rule for a message that is
already deleted.

**No time window on either action.** An edit sets `edited_at`, which the UI shows
as an "edited" marker, so a late edit is visible rather than silent — that
visibility is what a window would otherwise have bought, at the cost of a number
nobody could justify.

**Editing is the author's alone; deleting is the author's or a channel admin's.**
The asymmetry is the point: deleting someone's words is moderation, rewriting
them under their name is forgery. No role on this platform can edit a message it
did not write.

##### Outcomes

| Case | Result |
|---|---|
| the message's channel is not visible | **404** `not-found` |
| the message id does not exist | **404** — the same body, deliberately, so an id cannot be probed |
| the channel is archived | **404** — see the freeze below |
| `PATCH`, caller is not the author | **403** `forbidden` |
| `PATCH`, caller is a channel admin but not the author | **403** — admins delete, they do not edit |
| `PATCH`, the message is already deleted | **409** `conflict`, "This message was deleted." |
| `PATCH`, the version does not match | **409** `conflict` |
| `DELETE`, caller is neither the author nor an admin of the channel | **403** `forbidden` |
| `DELETE`, caller is the author or a channel admin | **200** with the tombstone |

**The order is load-bearing.** Visibility, then existence, then state, then
authority. Checking authorship first would answer "you are not the author" for a
message in a private channel the caller has never been in, which tells them the
message is there. `detail` names the rule and never the author.

**403 here, and not the 404 the channel rules use.** A message the caller cannot
see never reaches the authority check; one they *can* see is already on their
screen, so refusing the edit discloses nothing and a 404 would be a lie about a
row they are looking at.

##### The request

```jsonc
// EditMessageRequest — both fields required
{ "body": "the new text",   // the replacement, not a patch of the old one
  "version": 3 }            // a precondition, never an assignment
```

**Not a JSON Merge Patch of `Message`**, despite Conventions §4 defining `PATCH`
that way — under RFC 7386 `{"version": 3}` would mean *assign 3 to version*,
which is the opposite of what it means here. Both fields are required: there is
exactly one editable field on a message, so "absent means leave it alone" has
nothing to express. The body is held to the same rules a send is (§3.1.3).

##### Tombstones in history

| Row state | `body` | `attachments` | `editedAt` | `deletedAt` |
|---|---|---|---|---|
| live | the text | the files, in order | `null`, or when last edited | `null` |
| deleted | **`""`** — empty string, never `null`, never the original text | **`[]`** | unchanged | the delete time |

**A tombstone shows no attachments** — in the delete response, in the `message_deleted`
payload and in history — and mints no download URL. The `message_attachments` rows and the
blobs stay (nothing sweeps them: register D16, 🔴). **An edit keeps the attachments:** it
changes the text and nothing else.

##### Downloading an attachment — added 2026-10 (register D43)

`GET /api/v1/messages/{messageId}/attachments/{assetId}/download-url` → `200 {url, expiresAt}`,
a URL for **15 minutes** (stale at 780 s, as far as the SPA is concerned). **Asset has no public
download route, so this is the only way to a file's bytes**, and it is where visibility is
checked: anyone who can see the message's channel gets a URL.

| Case | Result |
|---|---|
| no such message, or its channel is not visible | **404** "No such channel." — the existing probe-proof wording |
| the message is deleted | **404** "No such attachment." — Messaging's own tombstone, without asking Asset (which would mint a URL) |
| the asset is not on this message | **404** "No such attachment." — Messaging's own record decides, so an id from elsewhere cannot mint a URL through this message |
| Asset answers 404 | **404** "No such attachment." |
| Asset unreachable | **503** |

The redaction is **server-side**, in the response mapper, so the text cannot
reach a client whatever the column holds. The client renders "This message was
deleted" from `deletedAt`, not from an empty body — and shows **no** edited
marker on a deleted row even when `editedAt` is set, because "This message was
deleted (edited)" is not something anyone needs to read.

`DELETE` returns **200 with the tombstone rather than 204**, and that is a
deliberate deviation from the platform habit. A delete here does not remove a row
from the list, so the client has to draw something; with 204 it would have to
refetch a page it is already holding to learn what.

**Deleting twice is a no-op.** The second call returns the same tombstone — same
timestamp, same version. The first delete bumps `version`; a repeat does not,
because the Elasticsearch external version should not move for a document that
did not change.

**The stored `body` is never cleared.** The `UPDATE` sets `deleted_at` and
`version` and touches nothing else. Blanking the column looks tidy, changes
nothing a client can see, and destroys data silently — and hard deletion belongs
to a retention job whose window is **D16, still 🔴**. Nothing in this scope
deletes a tombstone.

##### Archiving a channel freezes its messages, permanently

Every message route goes through the channel visibility query, which filters
`archived_at IS NULL`. So once a channel is archived, **nobody can edit or delete
anything in it — not the author, not an admin — and the attempt returns 404.**

That is the right default for an archive, and there is no remedy in this scope:
archiving is one-way (§3.1.1), so there is no unarchive route to point anyone at.
Stated here rather than left to become a support ticket.

#### 3.1.5 Not built in this scope — added 2026-08-16

The table in §3.1 is the eventual surface. These rows have no implementation
after the messaging core slices, and are listed here so a reader consulting the
design doc — rather than a plan or a service README — knows which is which.

| Row | Why it is not built | Register |
|---|---|---|
| `POST /internal/messages/sweep` | retention values are unset, and nothing hard-deletes a message | D16 🔴 |

One *column* ships ahead of its feature, because adding a column later rewrites a table
and adding an index or a route later does not: `thread_root_id` on `messages`.
(`last_read_id` on `channel_members` was a second, dropped unused when read state was built
in a table of its own — §3.1.7. `messages.attachments uuid[]` was a third: nothing ever
wrote to it, and it was dropped in migration `0006` when attachments were built — §4.)

#### 3.1.6 Search — added 2026-09-14

`GET /api/v1/search/messages?q=&limit=&cursor=` with plain `require_user`; searching is a
read, outside the fail-closed denylist set. **The index is a candidate list, not a source of
truth** — see the [ADR](../adr/260914-message-search-index-is-a-candidate-list.md).

- **`q`** is required, at most 200 characters, and must not be blank after trimming (400
  `validation-error` against `errors.q`). Every word must match (`match` with `operator: and`);
  no query syntax is exposed.
- **Visibility is decided per request, never stored in the index.** `channels.visible_ids`
  runs the same visibility query as every other read — public channels in the `wsp`
  workspace plus private channels the caller is in, archived excluded — and the Elasticsearch
  query is filtered to those ids, the claim's workspace and `deleted: false`. Removing someone
  from a private channel or archiving one takes effect in search immediately. A caller who
  can see no channels gets an empty page without Elasticsearch being asked. `terms` accepts up
  to `index.max_terms_count` values (65 536 by default), far above any workspace's channel
  count.
- **Newest first.** Sorted on `messageId` descending — UUID v7 in fixed-length lowercase hex
  sorts in time order — with `search_after` as the cursor: the same keyset shape as history.
- **Results come from Postgres.** Elasticsearch returns ids only; they are loaded with
  `deleted_at IS NULL` and the visible channel filter, and returned as ordinary `Message`
  DTOs in Elasticsearch's order. Index lag therefore cannot show a deleted message's text.
  (This `deleted_at` filter is not the history exception from Conventions §3: search returns
  no tombstones.) Replies are dropped here too (`thread_root_id IS NULL`, §3.2.4): they are not
  searchable in v1.
- **A page can hold fewer than `limit` items** when hydration drops a hit. `nextCursor` comes
  from the Elasticsearch hits, so nothing is skipped; only `nextCursor: null` means the end.
- **Failures.** Elasticsearch unreachable or erroring → 503 `service-unavailable`,
  `"Search is unavailable."`. The alias not existing yet (the Worker has never run) → an empty
  page. Elasticsearch is **not** a readiness dependency of this service: an outage degrades
  search and must not take chat out of rotation.
- **Recall is only as good as the index.** Enqueue is fire-and-forget (§5), so a job lost to
  an R3 outage is a message search never finds until a reindex path exists (register D29 🔴).

#### 3.1.7 Read state — added 2026-09-15

Register **D31** is settled — see the
[ADR](../adr/260915-read-state-follows-channel-visibility.md). The doc gave one
table row, one socket event, one column and "unread counts are derived", and
none of them said who may mark a channel read, what counts as unread, or who is
told.

- **Visibility gates it, not membership.** Anyone who can see a channel may mark
  it read — the same test as reading its history and posting in it (§3.1.1).
  The pointer lives in its own table, `channel_reads`, not on `channel_members`:
  nobody can join a channel themselves, so a membership column would give most
  people reading a public channel no unread count at all. `0003_channel_reads`
  drops the `last_read_id` column `0001` had shipped unused.
- **`POST /channels/{id}/read`** takes `{ "messageId": "uuid" }` and answers
  **204** with no body. The message must be in that channel, and must not be a
  thread reply — a reply is the same 404 (§3.2.4). A channel the
  caller cannot see, a message from another channel and an unknown id are all
  the same 404, `"No such channel."`, so an id cannot be probed. A tombstone may
  be marked read — it is part of the history.
- **The marker only moves forward.** Marking an older message than the current
  marker is a 204 that changes nothing: two tabs racing each other is the normal
  case, not a conflict. This stands in for Conventions §3's `version` column on
  this table — the upsert is guarded by `last_read_id < excluded.last_read_id`,
  so there is no lost update to detect and nothing for a client to send back.
- **Unread** is every message after the marker that **someone else** wrote and
  that **is not deleted** and **is not a thread reply** (replies never count as
  unread, §3.2.4); with no marker, every such message in the channel.
  The count is exact and uncapped, so a public channel nobody has opened counts
  its whole history — the first thing to revisit if the sidebar gets slow.
- **Only the reads that return a `Channel` pay for the count** — the list,
  detail, the re-read after a rename, and archive. The visibility guard every
  write authorizes through does not.
- **Receipts go to the reader, never the channel.** A read that moved the marker
  broadcasts `read_receipt_updated` to `user:{workspaceId}:{userId}` — that
  person's own connections in this workspace, which every connection joins on
  connect. A read over the socket skips the connection it came from. Nobody
  learns how far anyone else has read.
- **Sending a message does not move your own marker.** It does not need to: your
  own messages are never in your count.

### 3.2 Socket.IO namespace — `/messaging`

Real-time runs on the Socket.IO `/messaging` namespace (Conventions §6). Client→server
events are verbs; server→client events are past-tense facts. `send_message` returns the
created `Message` via the Socket.IO acknowledgement callback.

**WebSocket only — added 2026-09-14 (register D30).** `build_server` passes
`transports=["websocket"]`, so a long-polling handshake is refused rather than served, and
the chart sets no session affinity. See Conventions §6.

**Client → Server**

| Event | Args | Effect |
|--------|------|--------|
| `join_channel` | channelId | Authorize + join room `channel:{id}`. |
| `leave_channel` | channelId | Leave room. |
| `send_message` | `{ channelId, body }` — **narrowed 2026-08-16** | Persist + broadcast. Acks the created `Message`. |
| `edit_message` | `{ messageId, body, version }` — **`version` added 2026-08-16** | Author-only edit + broadcast. Acks the edited `Message`. |
| `delete_message` | `{ messageId }` | Author/channel-admin delete + broadcast. Acks the **tombstoned `Message`**. |
| ~~`add_reaction` / `remove_reaction`~~ | — | **Not built (2026-09-16, D39).** Reactions are written over REST only. The socket writes that exist earn their place by needing ack-and-reconcile against an optimistic `temp:` id; a toggle does not. The server still broadcasts `reaction_changed`. |
| `mark_read` | `{ channelId, messageId }` | Move the read marker forward; acks `{ ok: true }`. If it moved, broadcast `read_receipt_updated` to the reader's own room, skipping this connection — §3.1.7. |
| `typing` | `{ channelId }` | Ephemeral; fan out `user_typing` (not persisted). Authorized on channel visibility, like every write — an event for a channel the sender cannot see is dropped silently, since there is no ack to carry a 404. |

**Server → Client (events)**

| Event | Payload |
|-------|---------|
| `message_received` | `Message` |
| `message_edited` | `Message` |
| `message_deleted` | `Message`, redacted — **corrected 2026-08-16**, see below |
| `reaction_changed` | `{ messageId, channelId, emoji, count, userId, reacted }` — **corrected 2026-09-16.** The **authoritative count**, not a delta: the person who clicked applies their own change up to three times (optimistically, from the response, from their own echo), so a delta would treble it. `userId` and `reacted` describe that one person; every other client ignores them. Deliberately **not** a `Message` — `reactions[].reacted` is per-caller and a room emit sends one payload to everybody |
| `read_receipt_updated` | `{ channelId, userId, messageId }` — to room `user:{workspaceId}:{userId}` only, never the channel's |
| `user_typing` | `{ channelId, userId }` — see §3.2.4 |
| `channel_added` | `{ channelId }` — **added 2026-10-05.** A direct message has its first top-level message and is about to be listed. To room `user:{workspaceId}:{userId}` of **both** members only (all their tabs), never the channel's room, after `message_received` and after commit. At least once: two simultaneous first sends may both emit. The SPA refetches its channel list |

Rooms and naming follow Conventions §6. Presence (online/away) is published to R2 and
mirrored to the Canvas service's presence as needed (shared R2).

#### 3.2.1 How the namespace is built — added 2026-08-16

**The R2 backplane names its own channel: `AsyncRedisManager(url,
channel="messaging")`.** The constructor defaults to `channel="socketio"`, and
Canvas puts its backplane on the same R2 instance (doc 03 §4.1) — so two
services on the default would deliver every Canvas emit into this process to be
re-dispatched against these rooms. `doc:{id}` does not match `channel:{id}`
today, so nothing visibly breaks, which is exactly what makes it worth fixing
now: it becomes a cross-service leak the first time either service names a room
the other could name too. **Canvas needs the same change** and is told rather
than edited from here. The general rule is in Conventions §6.

**`cors_allowed_origins` is passed as `settings.cors_allowed_origins or None`.**
Conventions §5.6 makes an empty list mean "install no CORS at all" — a service
behind one ingress shares its SPA's origin. engine.io reads an empty list as an
allow-list containing nothing and refuses every browser handshake with a 400.
`None` is its spelling of "same origin only". The bug would only appear in the
deployment the convention was written for.

**The Socket.IO ASGI app wraps FastAPI and must be constructed with
`other_asgi_app` alone.** `ASGIApp` handles the `lifespan` scope itself and only
delegates it down when it was given neither `on_startup` nor `on_shutdown`, so
adding either would silently stop the FastAPI lifespan running and leak a
connection pool per process with no error anywhere. Everything that is not the
engine.io path falls through, so `/health/live` still answers through the
wrapper.

#### 3.2.2 The handshake — added 2026-08-16

The token comes from the handshake `auth` payload, falling back to an
`access_token` query parameter (Conventions §6); the fallback is second because
a query string ends up in access logs. It is verified with the same core
`require_user` uses, with **`sensitive=False`** — channel membership is not
workspace membership, so none of this surface is in Conventions §5.2's
fail-closed set, and an unreachable R1 accepts the connection exactly as it
accepts a `GET /channels`.

A refused handshake raises `ConnectionRefusedError`, which reaches the browser
as `connect_error`. **The SPA stops on `connect_error` rather than retrying:** a
handshake the server refused because a token is expired or denied will be
refused identically on every retry, and Socket.IO's backoff would hide that
behind a spinner forever. A dropped *transport* keeps the built-in backoff.

**The connection keeps the workspace of the token that opened it** (Conventions
§5.4). No handler reads a workspace from an event payload, for the same reason
no router reads one from a path.

**A connection is verified once, and mid-connection revocation is deliberately
not built.** An access token lives fifteen minutes and a connection can outlive
it, so a revoked user keeps receiving broadcasts until their client reconnects.
Closing that would need either a denylist round trip per emit — on the hot path,
per recipient — or an R2 fan-out of revocations, and the SPA re-establishes the
socket whenever the access token changes, which it does about a minute before
every expiry. The exposure is bounded by one token lifetime on a connection the
client re-opens on that cadence anyway.

**Known limitation: removing someone from a private channel does not evict their
live socket** from `channel:{id}`, so they keep receiving its broadcasts until
they next reconnect. Accepted rather than fixed: evicting a live connection needs
a registry of sids per user or a re-authorization on every publish, and the
exposure is one already-authorized session on one private channel. Public
channels are workspace-visible anyway, so there is nothing to revoke there. The
mitigation that already exists is that `join_channel` re-authorizes, so a
reconnect drops them.

#### 3.2.3 Rooms, acks and payloads — added 2026-08-16

**`join_channel` authorizes on channel *visibility*, not membership** — the room
mirrors the read rule in §3.1.1. A channel the caller cannot see acks a **404**
and never a 403. `leave_channel` needs no authorization: leaving a room you
should not be in is the correct outcome.

**The acknowledgement envelope**, which no document previously defined:

```jsonc
{ "ok": true,  "data": { /* the Message DTO, or absent */ } }
{ "ok": false, "problem": { /* the RFC 7807 body, verbatim */ } }
```

`problem` carries the same Problem Details document a REST call would have
returned (Conventions §4.2), so the platform has one error vocabulary rather
than one for HTTP and another for sockets — minus `instance` and `traceId`,
which a socket handler has nothing to derive from and must not invent.
**Handlers never raise:** a raising Socket.IO handler drops the client's
callback and the browser waits forever.

**Every message payload is `MessageResponse.model_dump(mode="json",
by_alias=True)`** — byte for byte the camelCase shape the REST route returns.
The SPA writes socket events and REST responses into the same cache entry and
reads both through one generated type, so two casings would be a render bug per
message rather than a caught error.

**`message_deleted` carries the full redacted `Message`, not
`{messageId, channelId}`.** A delete is a state transition of a row that stays
in the history (§3.1.4), so a client holding only an id could do nothing but
remove the row — the behaviour the tombstone exists to prevent — or refetch,
which defeats the point of the event.

**Reconnecting re-joins the room but replays nothing.** python-socketio has no
connection-state recovery, so everything broadcast while a client was away went
to a room it was not in and is gone. **Every connect therefore both re-joins the
active channel and refetches its history**; the refetch is the recovery and the
re-join only resumes the live stream from that point. The client refetches **once
`join_channel` has acked `ok`**, not alongside the emit: the room is entered only
after the visibility check, so the ack is the first moment broadcasts are
guaranteed to arrive (corrected 2026-09-15; doc 06 §5.2).

#### 3.2.4 The write path — added 2026-08-16

**`send_message` takes `{ channelId, body, threadRootId?, attachmentIds? }`.** `threadRootId`
(built 2026-10-02, D8a) makes the message a reply, normalised under its root as
the REST route does; an unknown root or one in another channel acks a 404 "No
such thread." **`attachmentIds` is built (2026-10, issue 4)** and
follows §3.1.3's rules exactly — the same domain functions, the same order (validate →
claim → insert → commit → publish). The SPA sends the field **only when there are
attachments**, so a plain send is the payload it always was. A refused claim or an
unreachable Asset is acked as the same Problem the REST route returns: **409** with the
reason in `detail`, **503** "Attachments can't be checked right now. Nothing was sent."
The ack and the `message_received` broadcast carry the same `attachments`.

**Thread events — added 2026-10-02.** `thread_summary_changed` →
`{ channelId, rootId, replyCount, lastReplyAt }` to `channel:{channelId}`,
published on every reply create and every reply delete that tombstoned, over REST
and the socket alike. It is an idempotent set, read **after** the reply's commit
so the last writer to commit counts everyone committed before it. Replies reach
the room as `message_received`/`message_edited`/`message_deleted` carrying
`threadRootId`. `reaction_changed` gains `threadRootId` (`null` on a top-level
message) so a client writes the right cache. `mark_read` naming a reply acks a 404
and the marker does not move; replies never count as unread.

**`edit_message` carries `version`, which this table omitted.** The expected
version is required on `PATCH /messages/{id}` (§4), and an event without one
would make the socket the way to lose someone else's edit silently. One rule,
two transports. `delete_message` stays unconditional, matching `DELETE`.

**A write is authorized on channel *visibility*, not on room membership.** A
room is per-`sid` in-memory state that a reconnect destroys and the client
re-establishes, so a send across a reconnect would race its own `join_channel`
and fail for a reason no user could act on — and gating on membership would make
the socket stricter than the REST route it replaces, resurrecting the bug
§3.1.1 closed. A room decides who *receives* a broadcast and nothing else. The
sender gets their ack whether or not they are in the room.

**Every inbound write re-checks the token.** The handshake authenticates the
connection once, and a connection outlives its fifteen-minute token. That was
tolerable while the socket could only read:

| Check | When | On failure |
|---|---|---|
| the principal has not expired | every inbound event, **including `typing`** | `unauthorized` ack, 401 |
| the token is not on the denylist | the four write events only — `send_message`, `edit_message`, `delete_message`, `mark_read` | revoked → 401 · unreachable R1 → **proceed** |

The denylist **fails open** here, matching §3.1: channel writes are outside
Conventions §5.2's fail-closed set. `typing` skips it because it persists
nothing and one Redis round trip per throttle window is real load for no
authority gained. **The server does not disconnect the socket itself** — acking
and then disconnecting in the same handler races the ack's own flush; the client
tears the connection down when it sees a 401 and reconnects with a fresh token.

**`typing` and `user_typing` — the payload is unchanged, the behaviour is
this.** There is no `typing_stopped` event and there is not meant to be one: a
server tracking who is typing would need that state shared across pods through
R2 for something this document calls ephemeral, and would still have to invent a
timeout for the client that closed its laptop mid-word. So:

- the client throttles `typing` on the **leading edge**, one emit per 2s window,
  because a trailing debounce would delay the indicator by its own window;
- the receiver drops a user 4s after their last `user_typing` — two missed
  windows;
- the server checks the channel is **visible** to the sender, workspace from the
  token, before fanning out — one query per event, bounded by the throttle. An
  event for a channel they cannot see (another workspace's, a private one they
  are not in) is **dropped silently**: a room says who receives, not who may
  send (corrected 2026-09-15);
- fan-out uses `skip_sid`, so a sender never sees their own indicator, **and**
  the client discards any `user_typing` carrying its own `userId`, which also
  covers that person's second tab;
- the payload carries **no display name**. Messaging holds none, and the browser
  already has the workspace directory it resolves every other name from. Two
  sources for one name is drift, even for an event that cannot go stale.

---

## 4. Data Model (PostgreSQL)

```sql
CREATE TABLE channels (
    id           uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    name         text NOT NULL,
    topic        text NULL,
    kind         text NOT NULL DEFAULT 'public',  -- public | private | dm
    created_by   uuid NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    archived_at  timestamptz NULL,
    version      integer NOT NULL DEFAULT 0
);

-- A partial index, not a table constraint: PostgreSQL has no
-- `UNIQUE (...) WHERE ...` on a constraint, only on an index. Names are unique
-- among public channels; private channels may repeat one. A DM's name is its
-- pair key `dm:{low}:{high}`, unique per workspace (below).
--
-- Indexes `lower(name)`, not `name` (corrected 2026-08-15): #General and
-- #general are the same channel. The stored name keeps the case it was typed
-- with — only the comparison folds.
CREATE UNIQUE INDEX ux_channels_public_name
    ON channels (workspace_id, lower(name)) WHERE kind = 'public';

-- Added 2026-10-05. One DM per pair of people: get-or-create's ON CONFLICT
-- names this index (migration 0007).
CREATE UNIQUE INDEX ux_channels_dm_pair
    ON channels (workspace_id, name) WHERE kind = 'dm';

-- Added 2026-08-15. The sidebar reads one workspace's unarchived channels in
-- name order on every page load, and nothing above covers that.
CREATE INDEX ix_channels_workspace_name
    ON channels (workspace_id, name, id) WHERE archived_at IS NULL;

-- `version` and `updated_at`, added 2026-08-16 while building the writes.
--
-- `version` is optimistic concurrency, not a decoration. Every update is
-- guarded — `WHERE id = :id AND version = :expected`, zero rows affected → 409
-- `conflict` — and bumps the column. The expected version travels in the
-- request body as `version`, not in an `If-Match` header: nothing on this
-- platform emits or parses an ETag, and the DTO already carries the number the
-- client holds. `DELETE` is the exception and is unconditional; it still bumps,
-- because the Elasticsearch external version (register D25) depends on it.
--
-- **The version check is not the existence check.** A zero-row update means
-- either a stale version or a row that is not there, so the order is fixed:
-- visibility (404), then role (403), then the guarded update (409). Answering
-- 409 for a channel in another workspace would confirm it exists.
--
-- `updated_at` has a `server_default` and deliberately no `onupdate` — an
-- `onupdate` fires on any flush, including ones nobody asked for — so every
-- update in the service sets it explicitly. Miss it and the column reads as the
-- creation time forever.

CREATE TABLE channel_members (
    channel_id   uuid NOT NULL REFERENCES channels(id),
    user_id      uuid NOT NULL,
    role         text NOT NULL DEFAULT 'member',  -- admin | member
    joined_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (channel_id, user_id)
);

-- Added 2026-08-15. The primary key leads with channel_id, so it answers "who
-- is in this channel?" but not "which channels is this user in?" — which is the
-- query the sidebar runs for every signed-in user.
CREATE INDEX ix_channel_members_user ON channel_members (user_id, channel_id);

-- Added 2026-09-15 (register D31, §3.1.7), replacing `channel_members.last_read_id`.
-- Keyed on visibility, not membership: anyone who can see a channel has a place
-- they have read up to. No `version` — the upsert only ever moves `last_read_id`
-- forward, so there is no lost update to catch. No foreign key on `last_read_id`,
-- so a retention job (D16) can hard-delete the message it points at.
CREATE TABLE channel_reads (
    channel_id   uuid NOT NULL REFERENCES channels(id),
    user_id      uuid NOT NULL,
    last_read_id uuid NOT NULL,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (channel_id, user_id)
);

CREATE TABLE messages (
    id             uuid PRIMARY KEY,                -- UUID v7 → time-ordered
    channel_id     uuid NOT NULL REFERENCES channels(id),
    author_id      uuid NOT NULL,
    thread_root_id uuid NULL REFERENCES messages(id), -- NULL = top-level
    body           text NOT NULL,
    -- `attachments uuid[]` was here until migration 0006 (2026-10): never written, replaced
    -- by `message_attachments` below.
    created_at     timestamptz NOT NULL DEFAULT now(),
    edited_at      timestamptz NULL,
    deleted_at     timestamptz NULL,
    version        integer NOT NULL DEFAULT 0   -- bumped on edit/delete
);
-- Corrected 2026-08-16, when `0002_messages` was written. The predicate this
-- index used to carry — `WHERE deleted_at IS NULL` — is wrong for this service:
-- history returns tombstones, so the query has no such clause and would not
-- match a partial index. The failure mode is a full scan on a busy channel,
-- which no test that only checks results would catch.
CREATE INDEX ix_messages_channel_time ON messages (channel_id, id DESC);

-- Built 2026-10-02 in migration 0005 (D8a). Partial: top-level rows, almost all
-- of the table, never enter it. Serves the per-page reply summary
-- (`GROUP BY thread_root_id`) and the replies page's keyset alike. Replies are
-- kept out of history, unread and search hydration by `thread_root_id IS NULL`.
CREATE INDEX ix_messages_thread ON messages (thread_root_id, id) WHERE thread_root_id IS NOT NULL;

-- Built 2026-09-16 in migration 0004 (register D39), and named
-- `message_reactions` rather than `reactions`: these are reactions *to
-- messages*, and a canvas or a file may want their own later.
--
-- The composite primary key is the concurrency control. Adding is
-- `ON CONFLICT DO NOTHING`, removing is a plain DELETE, so a double-click, a
-- retried request and two tabs racing all converge — which is why there is no
-- `version` column and nothing to conflict on. No `deleted_at` either:
-- removing a reaction is a real delete, and a tombstone here would be a row
-- nobody may ever read. No index beyond the key: every read groups by
-- `message_id`, which leads it.
CREATE TABLE message_reactions (
    message_id   uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    user_id      uuid NOT NULL,
    emoji        varchar(32) NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (message_id, user_id, emoji)
);

-- Built 2026-10 in migration 0006 (issue 4, register D43). A SNAPSHOT of what Asset said when
-- the message claimed the file, so a page of history costs one grouped query here and no call
-- to Asset, and a chip cannot change under a message. Keyed by message and attach order.
-- `asset_id` is UNIQUE — a second guard behind Asset's claim, and what refuses an id twice in
-- one send — and has no foreign key (it is Asset's row, Conventions §2). `message_id` does,
-- and cascades, so a future retention job (D16) cannot strand a row behind a hard delete.
CREATE TABLE message_attachments (
    message_id   uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    position     smallint NOT NULL,                  -- attach order, 0-based
    asset_id     uuid NOT NULL UNIQUE,
    file_name    text NOT NULL,
    content_type text NOT NULL,
    size_bytes   bigint NOT NULL,
    PRIMARY KEY (message_id, position)
);
```

`version` serves double duty. It is the optimistic-concurrency column Conventions §3 requires
of any updatable row, and it is what `jobs:index` carries as the Elasticsearch external
version (register D25) — so a late-arriving older document is rejected rather than applied.
Bump it on every edit and on delete.

**`channels` soft-deletes through `archived_at`, not `deleted_at`.** Conventions
§3 says mutable resources carry `deleted_at` and every query filters it; for
this table the equivalent column is `archived_at`, and `DELETE /channels/{id}`
sets it. Reads filter `archived_at IS NULL`. Called out because the blanket rule
sends people looking for a column that is not there.

**`messages` is the other exception, and it runs the opposite way.** The table
*has* `deleted_at`, and the read path deliberately does **not** filter it: a
deleted message stays in history as a tombstone with its `body` redacted to `""`
server-side, so the conversation around it still makes sense and a reload does
not bring the words back. Two exceptions to one Conventions §3 rule in one
service is worth stating plainly: the rule is "filter the soft-delete column
unless this document says otherwise", and both places it says otherwise are
here.

Threading is single-level: a reply sets `thread_root_id` to the top-level message; replies to
replies still point at the root. Read state is a per-person, per-channel pointer in
`channel_reads` that only moves forward; unread counts are derived per request — messages after
the pointer, written by someone else, not deleted (§3.1.7).

### 4.1 Redis usage
- **R1:** cache channel membership sets and recent-message windows for fast event authorization.
- **R2:** Socket.IO Redis manager (backplane) + presence pub/sub. **On the pub/sub
  channel `messaging`, not the `AsyncRedisManager` default** — Canvas shares this
  Redis instance and would otherwise share the channel name too (§3.2.1,
  Conventions §6).
- **R3:** `jobs:index` — one job per created/edited/deleted message for ES sync. The payload
  carries the whole document (§5), so these entries contain user-authored message bodies —
  see the retention and trimming note in Worker doc §8. The Worker `XDEL`s each entry once
  it is processed.

---

## 5. Internal Design — Send Message
Mirrors the architecture's sequence diagram:
1. Client emits the `send_message` event on the `/messaging` namespace.
2. Persist to `messages` (PostgreSQL).
3. Broadcast `message_received` to room `channel:{id}` via the R2 backplane.
4. `XADD jobs:index` with the **full indexable document**, not just an identifier:
   `{ messageId, channelId, workspaceId, authorId, body, createdAt, version }` under job type
   `message.upsert` (or `message.delete`). There is no `op` field — the job `type` says it.
   🟢 Register D25 — the Worker holds no database connection, and Messaging already has the
   message in hand here, so a read-back would add load to this exact path for nothing.
   `version` is the row's version, used as the Elasticsearch external version so two rapid
   edits cannot be indexed out of order. See the
   [ADR](../adr/260727-worker-never-reads-service-databases.md).
5. Worker consumes and indexes into Elasticsearch (Worker doc owns the mapping).

Edits/deletes follow the same persist → broadcast → enqueue pattern.

**Step 4 built 2026-09-14** (`messaging/indexing.py`), at all six write sites — send, edit and
delete over REST and over the socket — immediately after the broadcast.

- **Fire-and-forget** (Conventions §7). A failed `XADD` is logged with the message id and the
  exception class and swallowed; the write has already succeeded. The queue's Redis client
  uses ~1 s timeouts so an R3 outage cannot hang a request. The cost is recall: a lost job is
  a change search misses until a reindex path exists (register D29 🔴).
- **The job carries the committed response DTO**, so `message.delete` sends `body: ""` — R3
  never holds text a user asked to remove.
- **A repeat delete enqueues nothing.** It changes no version (§3.1.4), and
  `messages.delete` reports `deleted_now` so the producer can tell.
- **The workspace is the caller's `wsp` claim**; `messages` has no workspace column, and the
  visibility check behind the write proved the channel is in it.

---

## 6. Configuration
Common vars (Conventions §8): owns `POSTGRES_DSN`, uses `REDIS_CACHE_URL`,
`REDIS_REALTIME_URL`, `REDIS_STREAMS_URL`. Plus `MESSAGING_MAX_BODY_CHARS` (default 8000),
`MESSAGING_MAX_ATTACHMENTS` (default 10), and `ELASTICSEARCH_URL` — read-only, for
`GET /search/messages`, and deliberately not a readiness check (§3.1.6).

For attachments (2026-10): `ASSET_INTERNAL_URL` — Asset's **origin**, with no path (callers
append `/api/v1/internal/...`); `SERVICE_TOKEN_URL` — Auth's `service-token` endpoint;
`MESSAGING_SERVICE_CLIENT_ID` (default `messaging`) and `MESSAGING_SERVICE_CLIENT_SECRET`.
They mirror the Worker's `WORKER_SERVICE_CLIENT_*` and default to empty, so a deployment
without them starts and answers 503 to a send that names a file. Auth is told the same
client with scopes `assets:claim` and `assets:download` (`AUTH_SERVICE_CLIENTS`). **Asset is
not a readiness check:** a send with no files never calls it.

## 7. Cross-Cutting
Auth, errors, pagination, observability, health per Conventions. Metrics:
`messages_sent_total`, `messages_edited_total`, `reactions_total`, Socket.IO connection gauge.

## 8. Non-Functional & Limits
- Real-time delivery p99 < 500 ms end-to-end.
- Max message body 8000 chars; max 10 attachments; emoji from an allow-list.
- History reads served from Postgres; full-text from Elasticsearch.

## 9. Open Decisions
- Threading depth: single-level (assumed) vs. nested.
- ~~DM modelling: as `kind='dm'` channels (assumed) vs. separate table.~~ **Settled 2026-10-05**
  (register D8b): `kind='dm'` channels, one per pair — see §3.1.2.
- Whether `/search/messages` lives here (thin proxy) or clients query a dedicated search gateway.
- ~~Edit/delete windows and tombstone retention policy.~~ **Settled 2026-08-16
  (register D8d 🟢)** — no time window, author edits own, author or channel admin
  deletes, tombstones retained in history. See §3.1.4 and the
  [ADR](../adr/260816-message-edit-and-delete-semantics.md). **How long a
  tombstone is kept before hard deletion is still D16 🔴** and nothing here
  deletes one.
