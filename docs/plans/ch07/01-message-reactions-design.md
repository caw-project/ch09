# Message reactions — design

**Status:** Approved in brainstorming, 2026-09-16 · **Branch:** `feature/message-reactions`
**Worktree:** `/Users/elton/scm/manning/caw-reactions`, from `main` at `f0ba289`
**Touches:** Messaging (table, routes, aggregate query, broadcast), the SPA (bar, picker, cache), `tests/bdd`

## Context

Doc 02 names reactions in §3.1, §3.1.5 and §4 and nothing implements them. There is no table, no
route, no event and no component; `schemas.py:162` carries a docstring saying so and
`tests/integration/test_schema.py:30` actively asserts `"reactions" not in names`. Unusually for
this project, reactions have **no row in the open-decisions register at all** — not 🟢, not 🔴,
absent. So this slice makes the decision as well as building it (§8).

It was chosen over threads, DMs and the unbuilt search UI because it is the one remaining
Messaging feature that is a full vertical — migration, REST, a new server→client event, SPA state
and a journey — while being blocked by nothing. Canvas, assets, notifications and retention all
sit behind 🔴 decisions (D11/D21, D13/D15, D18+D28, D16).

### Decisions taken while designing

| Question | Answer |
|---|---|
| Which emoji | A **fixed server-owned allowlist of shortcodes**, not free unicode. Validation is a pure function over a constant; no NFC normalisation, no ZWJ or skin-tone question, no moderation surface |
| Write transport | **REST only**, with a socket broadcast out. The socket writes that exist (`send_message`, `edit_message`) earn their place by needing ack-and-reconcile against a `temp:` id; a toggle does not |
| How reactions reach a client | **Aggregated onto `MessageResponse`**, one grouped query per *page*. Not a second endpoint, which would mean 50 fetches for a 50-message page |
| Broadcast payload | **The authoritative count, not a delta** — see §5, this is the one decision that changed during design |
| Reacting to a tombstone | 409. The caller can already see the tombstone in history, so a 404 would be dishonest about why |
| Deleting a message | Deletes its reactions in the same transaction. A tombstone carries none, and no orphan count survives |
| Optimistic UI | Yes, and it is the first optimistic **REST** mutation in the SPA. It costs nothing extra: the cache writer has to exist for the broadcast anyway |

### Out of scope

Reacting over the socket; reactions on canvas objects; custom or per-workspace emoji; a
"who reacted" hover list (the DTO carries counts, not user ids — see §4); notifying an author that
their message was reacted to (D18 🔴); indexing reactions into Elasticsearch; reaction counts in
search result ordering; any change to threads, DMs or attachments.

---

## 1. Components

| Unit | Location | Purpose | Depends on |
|---|---|---|---|
| Allowlist + validation | `messaging/reactions.py` | `REACTION_EMOJI` constant; `validate(emoji) -> str` raising the 400 | — |
| Reaction domain | `messaging/reactions.py` | `add`, `remove`, `summaries_for(session, *, message_ids, user_id)`, `clear_for_message` | `models.Reaction` |
| Table | `messaging/models.py` — `Reaction` | `(message_id, user_id, emoji)` | `Base` |
| Migration | `messaging/alembic/versions/0004_reactions.py` | `message_reactions` | `0003` |
| DTO | `messaging/schemas.py` — `ReactionSummary`, `ReactionRequest`, `MessageResponse.reactions` | wire shape | `CamelModel`, `CamelRequest` |
| Routes | `messaging/routers/reactions.py` | `POST` / `DELETE` | `require_user`, `_visible_message` |
| Broadcast | `messaging/realtime.py` — `publish_reaction_changed` | `reaction_changed` to `channel:{id}` | existing `sio` |
| SPA bar + picker | `frontend/src/features/channels/ReactionBar.tsx`, `ReactionPicker.tsx` | render and toggle | generated types |
| SPA cache writer | `frontend/src/features/channels/useMessages.ts` — `applyReaction` | idempotent set | TanStack Query |

No new runtime dependency, no new environment variable, no chart change.

---

## 2. Data model

`message_reactions`, created by `0004_reactions.py` (`revision = "0004"`, `down_revision = "0003"`),
following the shape and the argue-it-in-the-docstring style of `0003_channel_reads.py`:

| Column | Type | |
|---|---|---|
| `message_id` | `UUID` | PK, `ForeignKey("messages.id")` |
| `user_id` | `UUID` | PK, **no FK** — Auth owns that row (Conventions §2) |
| `emoji` | `varchar(32)` | PK, a shortcode |
| `created_at` | `timestamptz` | `not null default now()` |

**The composite primary key is the feature's concurrency control.** Adding a reaction is
`INSERT … ON CONFLICT DO NOTHING`, so a double-click, a retried request and two tabs racing all
converge on one row; removing is a `DELETE` that succeeds whether or not a row was there. No
`version` column, because there is nothing to conflict on — which is the same argument D31 made
for the forward-only read marker, and it is recorded the same way.

`message_id` leads the key, so the group-by in §4 is served by the primary key index and the table
needs **no `__table_args__`** — as `ChannelRead` needs none.

**No `deleted_at`.** Removing a reaction is a real delete: there is no history requirement, nothing
renders a removed reaction, and a tombstone would only be a row nobody may read. CH009 does not
apply to a table without the column, and the migration docstring says why it is absent so the next
reader does not have to guess.

**The allowlist**, in `messaging/reactions.py`:

```python
REACTION_EMOJI: tuple[str, ...] = ("thumbsup", "heart", "tada", "smile", "eyes", "check")
```

Shortcodes rather than characters: a shortcode is stable, fixed-width, index-friendly, and leaves
the client free to render however it likes. An unknown, empty, uppercase or overlong value is a
**400** `validation-error` with `errors.emoji` — `ProblemException.validation_error` is 400 on this
platform (`shared/problems.py`), the same answer an empty message body gets, and an earlier draft
of this document said 422 in error. Widening the tuple later is a one-line change; narrowing it
would strand rows, so the set starts small.

---

## 3. REST

```
POST   /api/v1/messages/{message_id}/reactions          {"emoji": "thumbsup"}   → 200 MessageResponse
DELETE /api/v1/messages/{message_id}/reactions/{emoji}                          → 200 MessageResponse
```

`Depends(require_user)`. Neither is in the Conventions §5.2 fail-closed set — a reaction is not a
membership change — so the denylist fails open, as it does for sending a message.

- **The POST body is `ReactionRequest(CamelRequest)`** — one field, `emoji`, validated by
  `reactions.validate`. The DELETE takes it in the path instead, so removing needs no body.
- **Both return the full updated message.** `PATCH` and `DELETE` on a message already do, so the
  SPA reuses the existing `upsertMessage` cache writer and gains no second cache keyed by message.
- **Both are idempotent.** Reacting twice leaves one row and returns 200; removing a reaction that
  was never there returns 200 with the message unchanged. No 204: the caller wants the new counts.
- **Authorization is the existing `_visible_message` path** (`routers/messages.py:111-124`), which
  resolves the message, then the channel, and raises the same `"No such channel."` 404 for an
  unknown id, another workspace's row, an archived channel or a private channel the caller is not
  in. Anyone who can *see* the channel may react; there is no admin gate and no membership gate,
  matching how posting is gated (`messages.py:9-15`).
- **A tombstone is a 409** — `ProblemException.conflict("This message was deleted.")`. The decision
  is a pure function over the loaded row (`may_react(row) -> bool`), so it is provable at the unit
  layer without a database, per D32.
- **Deleting a message clears its reactions** in the same transaction as the tombstone, before the
  broadcast. `delete_message` therefore returns a message whose `reactions` is `[]`.

The route module goes in `main.py:124-130` beside the others.

---

## 4. The DTO and the aggregate

`MessageResponse` (`schemas.py:157-192`) gains one field:

```python
reactions: list[ReactionSummary]     # always present; [] when there are none
```

```python
class ReactionSummary(CamelModel):
    emoji: str      # a shortcode from REACTION_EMOJI
    count: int      # how many people, including the caller
    reacted: bool   # whether the caller is one of them
```

Required with no default, like every other field on that model, so the generated TypeScript needs
no null checks and `aMessage()` is forced by `tsc` to supply it.

**`count` and `reacted` only — no user ids.** A "who reacted" list is a second feature with its own
privacy question, and shipping ids to every client now would decide it silently.

**Ordering is allowlist order, not count order.** Chips must not swap places under the pointer as
counts change mid-click. `summaries_for` returns them in `REACTION_EMOJI` order, omitting zeroes.

`reactions.summaries_for(session, *, message_ids, user_id) -> dict[UUID, list[ReactionSummary]]`
runs **one grouped query for a whole page**:

```python
select(
    Reaction.message_id,
    Reaction.emoji,
    func.count().label("count"),
    func.bool_or(Reaction.user_id == user_id).label("reacted"),
).where(Reaction.message_id.in_(message_ids)).group_by(Reaction.message_id, Reaction.emoji)
```

It is called from the router, leaving `messages.history_page`'s `Page[Message]` signature alone —
the way `_with_read_state` was bolted onto channels rather than pushed into the paging helper.
`message_ids` empty short-circuits to `{}` without a query.

`_as_message` (`routers/messages.py:82-94`) gains a `reactions` argument and stays the single
construction site. Its nine call sites divide into three cases, and most of them pay nothing:

| Call site | What it passes |
|---|---|
| `list_messages` (`:143`), `search` hydration (`routers/search.py:70`) | one `summaries_for` over the page |
| `get_message` (`:194`), `edit_message` (`:250`), both reaction routes | `summaries_for` over one id |
| `send_message` (`:180`), `delete_message` (`:293`), `realtime_writes.py:200,246,276` | `[]` — a new message has none and a delete has just cleared them |

The indexing producer (`indexing.py:44-70`) reads only `id/channel_id/author_id/body/createdAt/
version` and is untouched: reactions are not indexed.

---

## 5. The broadcast

```
reaction_changed → { messageId, channelId, emoji, count, userId, reacted }
```

Emitted to `room(channel_id)` on `/messaging` by `publish_reaction_changed`, modelled on
`publish_read_receipt` (`realtime.py:322-349`) rather than `_publish`, because the payload is a
dict of facts and not a `MessageResponse`. Commit, then publish, as everywhere else.

**Why not broadcast the whole DTO,** which is what `message_deleted` does and would need no new SPA
handler at all: `reacted` is computed *for the caller*, and a room emit delivers one payload to
everyone. Every recipient would receive the actor's `reacted` and half the room would render its
own button lit. The DTO is per-caller by construction and cannot be broadcast.

**Why the authoritative `count` and not `action: "added" | "removed"`.** A delta must be applied
exactly once, and the actor has three chances to apply it — optimistically, from the REST response,
and from its own echo of the broadcast. Skipping the actor's socket does not fix it: a REST write
has no `sid` to skip, and the actor's other tabs need the event. Carrying the count makes applying
it an idempotent **set**, safe applied twice or out of order, from any tab, in any sequence.

`userId` and `reacted` are in the payload so each client can decide for itself: the count is
everyone's, the lit state is mine. **`reacted` was added while planning** — an authoritative count
carries no direction, so without it the actor's own client cannot tell which way its toggle went.
Every other recipient ignores both fields and takes only the count. It is a user id, which logs and
payloads may carry (CH008); nothing else
about the reactor is sent.

---

## 6. SPA

- **`ReactionBar`** renders under the message body in `MessageItem.tsx` — a chip per summary,
  `👍 3`, lit when `reacted`. Clicking a lit chip removes, an unlit one adds. Nothing renders when
  the list is empty, so an unreacted message looks exactly as it does today.
- **`ReactionPicker`** is one more button in the existing hover-controls span
  (`MessageItem.tsx:106-127`), opening the fixed six-emoji row. No popover library, no search box,
  no emoji-data dependency — the set is six.
- **Shortcode → glyph** is a client-side constant. The server never sends a character.
- **`useToggleReaction(accessToken, workspaceId, channelId)`** is hoisted to `MessageList`, one
  mutation for the whole list rather than one per row, following the rule stated at
  `MessageList.tsx:54-58`.
- **`applyReaction(queryClient, key, {messageId, emoji, count, userId}, myUserId)`** sets that
  emoji's count on the cached message, drops the chip at `count === 0`, re-sorts into allowlist
  order, and flips `reacted` only when `userId === myUserId`. It no-ops when nothing is cached,
  like `upsertMessage` (`useMessages.ts:103-128`).
- **Optimistic:** `onMutate` calls `applyReaction` with the predicted count, `onError` applies the
  inverse, `onSuccess` upserts the authoritative message from the response. Because the writer is
  an idempotent set rather than a delta, the later broadcast echo is harmless.
- **Live:** a `reaction_changed` handler in `useChannelSocket.ts` beside `onMessage` (`:134-149`),
  keyed off the event's `channelId`, and going through the same `reapplyAfterFetch` in-flight guard
  (`:76-85`) so an event landing during a history fetch is not lost.
- **Contract regen** after the routes exist: `python -m messaging.openapi >
  src/frontend/openapi/messaging.json`, then `npm run generate:api` (D23). `aMessage()` gains
  `reactions: []` and every MSW stub that returns a message is checked by `tsc`.

---

## 7. Tests

D32: the failing test goes at the lowest layer that can prove the behaviour, and the slice **stops
at red** for review before any production code exists.

**Unit — pytest** (`src/services/messaging/tests/unit/`). Three pure functions, which is where the
rules live:
- `validate`: each allowed shortcode; unknown, empty, uppercase, overlong, and a raw emoji
  character all rejected.
- summary shaping from grouped rows: allowlist ordering, zero counts omitted, `reacted` true only
  for the caller's own rows, empty input → `[]`.
- `may_react(row)`: false for a row with `deleted_at` set, true otherwise — a decision over the
  loaded row, never a faked session or repository.

**Unit — Vitest** (beside their source, queried by role and text, no `data-testid`):
- `applyReaction`: idempotent under repeat application, drops a chip at zero, flips `reacted` only
  for my user id, keeps allowlist order, no-ops on an empty cache.
- `useToggleReaction`: optimistic apply, then rollback against an MSW `problem` stub.
- `reaction_changed` through `serverEmit` landing in the cache, including while a fetch is in
  flight.
- `ReactionBar` renders counts and lit state; the glyph map covers every allowlist entry.

**Integration — testcontainers** (`src/services/messaging/tests/integration/`), using the existing
`client_for` / `ada` / `grace` fixtures:
- add and remove round trip; a second POST leaves the count at 1 (PK idempotency); removing
  something never added is a 200 no-op.
- 400 for an unknown emoji; 404 for a message in a channel the caller cannot see; 409 on a
  tombstone.
- deleting a message clears its reactions and returns `reactions: []`.
- a history page returns summaries **in one grouped query, not one per message** — asserted by
  counting queries, because the N+1 is the thing most likely to regress.
- `reacted` differs between ada and grace on the same row. This is the per-caller correctness that
  §5 exists to protect.
- search hydration carries reactions.
- `reaction_changed` arrives over a real socket with the right payload, via `serve`.
- `test_schema.py:30` flips from `not in` to `in`, with the column and `timestamptz` assertions the
  neighbouring tests use.

**End-to-end — one journey**, a new `tests/bdd/features/reactions.feature`: Ada reacts to a
message and Grace sees the count appear live. Selectors are `data-testid`, in the page object only;
the step definitions contain none. One scenario, because a field rule belongs lower down and the
suite was deliberately triaged to its key journeys.

---

## 8. Decisions and documentation, in this slice

**Register (`07-open-decisions-register.md`)** — a new row, **D39 🟢**, in the Messaging table:
*reactions — fixed shortcode allowlist, REST write with a socket broadcast, aggregated onto the
message DTO, counts without user ids.* It is the first entry for a feature the register never
covered, so it states the whole shape rather than settling one question.

**ADR** (`adr-writer`), `docs/adr/260916-message-reactions.md`: the three choices that hold each
other up — the composite primary key as the concurrency control, the authoritative count in the
broadcast rather than a delta, and the aggregate on the DTO rather than a second endpoint.

**Doc 02** — §3.1 gains the two routes; §3.1.5 loses the "not built" row; a new subsection for
reaction semantics (allowlist, idempotency, the tombstone 409, counts without ids); §3.2 adds
`reaction_changed`; §4 documents `message_reactions` and its absent `deleted_at` and `version`.

**Code docstrings** — `schemas.py:162` (the "no reactions" paragraph becomes the real thing),
`0001_channels.py:4-5` and `0002_messages.py:25` (both say reactions are not created yet),
`messaging/__init__.py`.

---

## 9. Verification

1. `scripts/test.sh` — lint, unit, integration — green, and `scripts/test.sh e2e` for the new
   journey. Unit coverage printed and not regressed.
2. `python3 .claude/hooks/checks/conventions.py` over everything changed: CH001 (workspace from the
   claim, never the path), CH004 (the 404 for an invisible message), CH007, CH008, CH009.
3. Manual, against `docker compose up -d --build`: react in one browser, watch the count appear in
   another; toggle off; react to a message then delete it and see the chips go; double-click a chip
   and confirm the count is 1; stop the socket and confirm the REST response still updates the bar.
4. The worktree is left dirty and uncommitted (CLAUDE.md).
