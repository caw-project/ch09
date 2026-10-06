# Direct messages — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** Any two people in a workspace can open the one DM they share from a **+** in the sidebar;
it works like a private channel with two fixed members, is named after the other person, and
appears live in both sidebars when its first message is sent.

**Architecture:** A DM is a `kind='dm'` channel (D8b) whose stored `name` is the pair key
`dm:{low}:{high}`, made unique per workspace by a partial unique index, so get-or-create is an
`INSERT … ON CONFLICT DO NOTHING` followed by a read. Both people get a `member` row and nobody an
`admin` row. `GET /channels` lists a DM only once it has a top-level message; `ChannelResponse`
gains `dmPartnerId`; the first top-level send into a DM emits `channel_added { channelId }` to both
members' personal rooms, and the SPA refetches its channel list on it. The SPA adds a *Direct
messages* section, a member picker, and names a DM after the other person everywhere.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, python-socketio, pytest +
testcontainers · React 19, TanStack Query 5.101, Vitest + MSW · pytest-bdd + Playwright.

**Issue:** `docs/plans/issue-5/00-issue.md` — read it first. This plan argues from it and does not
repeat it.

**Worktree:** `../caw-issue-5`, branch `feature/issue-5`, from `main` at `b192d9d`.

## Decisions

Decided by the issue:

| # | Question | Answer |
|---|---|---|
| 1 | Scope | R1–R11; *Not in this issue* stays out |
| 2 | Modelling | `kind='dm'` channels (D8b), 1:1 only |
| 3 | When a DM is listed | Once it has a top-level message, for both members; a tombstone counts |
| 4 | The live signal | `channel_added { channelId }` to both `user:{ws}:{userId}` rooms, at least once |
| 5 | The other user's id | Not checked against Auth, as add-member doesn't (a gap, recorded) |
| 6 | 🔴 entries | None depended on. D18 and D28 untouched |

Taken in this plan — each needs the plan-reviewer's yes or no:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 7 | How the pair is keyed | `channels.name = "dm:{low}:{high}"` (the two UUIDs sorted, canonical lowercase), with `ux_channels_dm_pair` unique on `(workspace_id, name) WHERE kind = 'dm'` | `name` is `NOT NULL` and unused for a DM (issue: "what goes in the unused `name`" is ours), rename is refused for a DM (R9) so it never moves, and the partner is a pure parse of it. Alternative: a new `dm_pair` column with a CHECK — one more column and a backfill-free migration either way; changing later is a migration that copies `name` into it |
| 8 | Concurrency of get-or-create (R2) | `INSERT … ON CONFLICT (workspace_id, name) WHERE kind = 'dm' DO NOTHING RETURNING id`; if no row, `SELECT` the existing id. Members inserted only by the transaction that created the channel | A racing insert blocks on the unique index until the winner commits, then does nothing; READ COMMITTED lets its next `SELECT` see the winner's row. Check-then-insert has a gap (`channels.create`'s docstring says the same) |
| 9 | The route | `POST /api/v1/channels/dm`, body `{ "userId": "uuid" }`, **200** with `ChannelResponse` whether found or created | Opening is idempotent and the client never needs to know which happened; a 200/201 split would give two racing callers different codes for the same outcome. Under `/api/v1/channels`, already in the Ingress allow-list (`charts/collabhub/templates/ingress.yaml:62`, checked) |
| 10 | DTO field | `dmPartnerId: uuid \| null`, required with no default (as `lastReadId`, doc 02 §3.1.3) | Computed per caller from the pair key: the other member on a DM, `null` on any other kind |
| 11 | Roles in a DM | Both rows `member`; no `admin` row | Issue §3.1.2 "no creator-as-admin". So `check_deletable` is author-only (R8) and the last-admin rule never fires |
| 12 | R9 refusals | **403** `"A direct message can't be renamed, archived or have its members changed."`, checked after the 404 and before `_admin_or_403` on `PATCH`/`DELETE /channels/{id}` and both member writes | A member's `myRole` is `member`, so today's guard already answers 403 "Only a channel admin can do that." — wrong reason, and a route that later relaxed admin-gating would open DMs. 409 was the alternative; 403 keeps one refusal code for "you can't change this channel" and the SPA already handles it |
| 13 | Self-DM (R3) | **400** validation error `"You can't start a direct message with yourself."`, `errors.userId` | A malformed request for this route, like a bad name on create. Nothing is written: refused before the insert |
| 14 | `POST /channels` with `kind: "dm"` | Still 400, unchanged; the two pinned tests keep their assertions and only their docstrings change | A DM is opened through its own route; creating one by name would skip the pair key. The issue's "they change with this issue" is read as the docstrings — **assumed**. Changing later is one branch in `validate_kind` |
| 15 | First-send detection (R10) | Before inserting, in the send's transaction: the channel is a DM, the message is top-level, and the channel has no top-level message yet. If so, publish `channel_added` after commit, after `message_received` | Under READ COMMITTED the first message to commit was checked before any other committed, so it always emits — at least once. Two concurrent first sends may both emit, which the issue allows. A count *after* commit could see 2 in both and emit none |
| 16 | `channel_added` while the list's first load is in flight | Invalidate; and if the list has no data and is fetching, invalidate again when that fetch settles | TanStack 5.101.4 cancels an in-flight fetch only when the query has data, otherwise returns the same promise (`query-core/src/query.ts:411-419`, checked) — so the first load could land without the DM (issue *Timing*) |
| 17 | Picker order — **assumed** | Workspace members minus the caller, sorted by display name (`localeCompare`) | The issue leaves the picker's UI to the plan. Directory order is join order, which means nothing to a person. One line to change |
| 18 | Where names come from in the SPA | Two pure helpers. `channelLabel(channel, nameFor)` is the **bare** name: `"general"` for a channel, the partner's display name for a DM — it goes in `data-channel-name`, `data-dm-name` and the header's text. `channelTitle(channel, nameFor)` adds the `#` for a channel only (`"#general"`, `"Grace Hopper"`) — the composer's `Message …` and a search result. Every R7 surface uses one of them | One rule, four call sites; `nameFor`'s `shortId` stub gives the *Naming and the directory* row for free. The `#` stays presentation, so `data-channel-name` is still `general` for a channel and the page objects every existing scenario uses (`chat_page.py:125`, `:175`, `:208`) still match. Alternative: one helper with the `#` in it — it breaks those 23 scenarios |
| 19 | Picker across a workspace switch | The mutation records the workspace it started in; on success it navigates only if that is still the current workspace, and invalidates only that workspace's list key | *Paths* row "Workspace switch". The list is keyed by workspace (D24), so the cache cannot leak; the navigation could |
| 20 | The register | D8b → 🟢; new **D44** 🟡 "Messaging does not check a `userId` against Auth on add-member or get-or-create" | Issue *Record in this slice*. 🟡 because the default is built and written down; deciding to check it is an Auth call nobody has made |

Nothing here builds on a 🔴 entry. The nearest is **D18** (notification channels): a DM's arrival
is signalled in the sidebar only, through `channel_added` and the existing badge — no notification,
push or email. **D28** (preferences) is why hiding a DM stays out: it would be per-user state.
**D16** (tombstone retention) is touched only in that a tombstone keeps a DM listed (R5), which holds
whatever retention later decides, since a hard-deleted DM message is out of scope.

## Corrections to the issue

None to the requirements. One reading recorded: the issue's *What exists already* says the
`kind='dm'` refusal tests "change with this issue"; decision 14 keeps their assertions.

## Test approach — recommendation to the test pair

**BDD outside-in, with one journey.** This is a large new capability a user sees and uses through
the SPA, and only two real browsers prove that a DM Ada starts appears in Grace's sidebar live and
carries a reply back. Write the journey first; everything under it goes down the pyramid.

| Behaviour | Layer | File |
|---|---|---|
| Ada starts a DM from **+** and sends; Grace, on #general, sees it appear with a badge, opens it and replies; Ada sees the reply live | **BDD** | `tests/bdd/features/direct_messages.feature` |
| Pair key, self-refusal, partner, fixed membership | unit | `messaging/tests/unit/test_dms.py` |
| `dmPartnerId` on the wire | unit | `messaging/tests/unit/test_dm_dto.py` |
| Get-or-create, concurrency, listing rule, DTO, R9 refusals, author-only delete, third-user 404s, everything a member can do | integration | `messaging/tests/integration/test_dms.py` |
| `channel_added` on each first-send path, to both rooms only; socket 404s; typing | integration | `messaging/tests/integration/test_dm_realtime.py` |
| DM search reaches members only | integration | `messaging/tests/integration/test_search.py` |
| The pair index | integration | `messaging/tests/integration/test_schema.py` |
| Naming, sorting, splitting helpers | Vitest | `features/channels/directMessages.test.ts` |
| Section, badge, picker, navigation, workspace switch | Vitest | `features/channels/DirectMessageList.test.tsx` |
| Header and view for a DM: name, no `#`, no controls, no member panel, placeholder | Vitest | `ChannelHeader.test.tsx`, `ChannelView.test.tsx` |
| `channel_added` → list refetch, both race orders, first load in flight | Vitest | `lib/realtime/useChannelSocket.dm.test.tsx` |
| A search result in a DM | Vitest | `features/search/SearchPage.test.tsx` |

**What no test here covers:** that two concurrent *first sends* can both emit — the race window is
too small to force, so the integration test proves only at-least-once. The 50-row first page of
`GET /channels` (the SPA fetches one page, `lib/api/messaging.ts:45`) can now be filled by DMs as
well as channels; that limit predates this work and is listed under *Not in this plan*.

**Baseline**, from `docs/test-report.md` at `bc3b5cfd3610-dirty`: Messaging unit 126 passed,
integration 276 passed; frontend (Vitest) 459 passed; end-to-end 23 passed. Expected counts below are
"N or more".

## Global constraints

- Workspace from the `wsp` claim only (CH001): the pair key is per workspace, and nothing reads a
  workspace from the body. A DM the caller isn't in is **404 `"No such channel."`**, never 403.
- `require_user` throughout; nothing here is in Conventions §5.2's fail-closed set.
- **Commit, then publish.** `channel_added` after `message_received`, both after commit; publishers
  no-op when `sio is None`.
- No foreign key to Auth's users; `dmPartnerId` is a bare id resolved by the SPA's directory.
- No new environment variable, chart or Compose change; no new table, so `tests/bdd/conftest.py`'s
  `TRUNCATE … CASCADE` on `channels` needs nothing (checked).
- The SPA: TanStack owns the list (D24); no channel copy in Zustand. Vitest queries by role, label
  or text; `data-testid`s below are for `ChatPage` only.

## File map

Paths are relative to `src/services/messaging/` and `src/frontend/src/` where shortened.

| File | Change | Responsibility | Task |
|---|---|---|---|
| `tests/unit/test_dms.py` · `tests/unit/test_dm_dto.py` | create | rules · wire shape | 1 |
| `tests/integration/test_dms.py` · `test_dm_realtime.py` | create | routes, SQL · socket | 2 |
| `tests/integration/test_search.py` · `test_schema.py` | modify | DM search · pair index | 2 |
| `tests/bdd/features/direct_messages.feature` · `steps/test_dm_steps.py` · `pages/chat_page.py` | create · create · modify | the journey | 3 |
| `features/channels/directMessages.test.ts` · `DirectMessageList.test.tsx` · `lib/realtime/useChannelSocket.dm.test.tsx` | create | the SPA's red | 3 |
| `ChannelHeader.test.tsx` · `ChannelList.test.tsx` · `ChannelView.test.tsx` · `search/SearchPage.test.tsx` · `test/factories.ts` | modify | DM cases; `label` in `renderHeader`; `aChannel` gains `dmPartnerId: null` | 3 |
| `messaging/dms.py` | create | pair key, partner, guards, `open_dm`, `opens_dm` | 4 |
| `messaging/models.py` · `alembic/versions/0007_dm_pair.py` | modify · create | the pair index | 4 |
| `messaging/channels.py` | modify | `VisibleChannel.dm_partner_id`; listing rule in `list_page` | 4 |
| `messaging/schemas.py` · `routers/channels.py` | modify | `OpenDmRequest`, `dmPartnerId`; the route; R9 guard | 5 |
| `routers/messages.py` · `realtime_writes.py` · `realtime.py` | modify | first-send detection; `authorized_channel` returns the channel; `publish_channel_added` | 5 |
| `src/frontend/openapi/messaging.json` · `src/types/messaging.ts` | regenerate | the contract | 5 |
| `lib/api/messaging.ts` | modify | `openDirectMessage` | 6 |
| `features/channels/directMessages.ts` · `DirectMessageList.tsx` | create | helpers · section and picker | 6 |
| `ChannelList.tsx` · `ChatLayout.tsx` · `ChannelHeader.tsx` · `ChannelView.tsx` · `MessageComposer.tsx` · `useChannels.ts` | modify | hide DMs from channels; mount the section; naming; `useOpenDirectMessage` | 6 |
| `search/SearchResult.tsx` · `search/useChannelNames.ts` · `search/SearchPage.tsx` | modify | a label, not a name | 6 |
| `lib/realtime/useChannelSocket.ts` | modify | `channel_added` | 6 |
| `MessageComposer.test.tsx` · `MessageComposer.attachments.test.tsx` (`:37`, `:256`) · `ChatLayout.test.tsx` · `ChatLayout.attachments.test.tsx` · `App.test.tsx` (the test at `:93`) · `CreateChannelDialog.test.tsx` (`:103-110`) · `ChannelList.test.tsx:50` | modify | **ripple**: composer prop `channelName` → `channelTitle`; `auth.members` stub wherever `ChatLayout` renders (the DM section loads the directory, and `setup.ts:32` fails an unstubbed request); `ChannelHeader`'s required `label` | 6 |
| `tests/unit/test_channel_rules.py:94-98` · `tests/integration/test_channels.py:169-174` | modify | docstrings only (decision 14) | 7 |
| `CreateChannelDialog.tsx:56` comment · `models.py:60-62` comment | modify | stale D8b wording | 7 |
| `docs/design/02-…`, `06-…`, `07-…` · `docs/adr/261005-direct-messages-are-dm-channels.md` · `docs/plans/ch06/gherkin/00-scenario-vocabulary.md` | modify · create · modify | the record | 7 |

Deliberately unchanged: `channels.visible_ids` and `_visible_query` (a DM is member-only already,
and search must include DMs — issue *What this assumes*); `tests/bdd/conftest.py`;
`tests/unit/test_read_markers.py:146`, because `_as_channel`'s signature does not change — the partner
rides on `VisibleChannel`.

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–3 | test-writer | failing unit, integration, Vitest and BDD tests, each failing for the reason given — **test-reviewer gate** |
| GREEN — backend | 4–5 | code-writer | Tasks 1–2 pass; contract regenerated |
| GREEN — SPA | 6 | code-writer | Task 3's Vitest passes; `tsc` clean |
| Finish | 7–8 | code-writer | the record, then verification (the journey's first run) |

One RED phase: Task 3's Vitest is typed from the contract in Task 2's interfaces. `aChannel()` gains
`dmPartnerId: null`, which `tsc` refuses until Task 5 regenerates — expected red, as the tests are.

---

## Task 1: The rules (RED)

**Files:** `src/services/messaging/tests/unit/test_dms.py`, `tests/unit/test_dm_dto.py` (create)

**Interfaces** — produces what Task 4 implements, in `messaging.dms`:
- `class SelfDmError(Exception)` · `class FixedChannelError(Exception)`
- `pair_name(a: uuid.UUID, b: uuid.UUID) -> str` — `f"dm:{low}:{high}"` of `sorted((a, b))`; raises
  `SelfDmError` when `a == b`
- `pair_of(channel: Channel) -> tuple[uuid.UUID, uuid.UUID] | None` — `None` unless `kind == "dm"`
- `partner_of(channel: Channel, user_id: uuid.UUID) -> uuid.UUID | None` — the pair member that
  isn't `user_id`; `None` on any other kind
- `check_manageable(channel: Channel) -> None` — raises `FixedChannelError` for a DM

And in `messaging.channels`: `VisibleChannel.dm_partner_id: uuid.UUID | None = None`.

`test_dms.py` (the whole file needs `messaging.dms`, so one load failure is the right red):

| Test | Proves | Expected red |
|---|---|---|
| `test_a_pair_has_one_name_whichever_way_round` | `pair_name(a, b) == pair_name(b, a)` and starts `dm:` | `ModuleNotFoundError: No module named 'messaging.dms'` |
| `test_pairs_sharing_one_person_have_different_names` | `(a, b)` ≠ `(a, c)` — a key of one id would pass the test above | same |
| `test_a_dm_with_yourself_is_refused` | `pair_name(a, a)` raises `SelfDmError`; `pair_name(a, b)` in the same test does not | same |
| `test_each_member_sees_the_other_as_partner` | `partner_of` both ways round, and `pair_of` gives `(low, high)`, on a DM built from `pair_name` | same |
| `test_only_a_dm_has_a_partner` | a `private` channel whose `name` is a `dm:` key gives `None` from `partner_of` and `pair_of` — kind decides, not the name | same |
| `test_a_dm_cannot_be_managed_and_a_channel_can` | `check_manageable` raises for `dm`, passes `public` and `private` | same |

`test_dm_dto.py`:

| Test | Proves | Expected red |
|---|---|---|
| `test_the_dto_carries_the_partner` | `_as_channel(VisibleChannel(…, dm_partner_id=GRACE))` dumps `"dmPartnerId": str(GRACE)` | `TypeError: VisibleChannel.__init__() got an unexpected keyword argument 'dm_partner_id'` |
| `test_a_channel_dto_has_a_null_partner_key` | a public channel dumps the key, value `None` — required, not omitted | `KeyError: 'dmPartnerId'` |

Build `Channel` rows directly, as `test_read_markers.py:130-141` does. House docstring on each.
Leave uncommitted.

## Task 2: The routes, the SQL and the socket (RED)

**Files:** `tests/integration/test_dms.py`, `test_dm_realtime.py` (create); `test_search.py`,
`test_schema.py` (modify)

**Interfaces** — the wire contract Tasks 3, 5 and 6 depend on:

```
POST /api/v1/channels/dm   { "userId": "uuid" }   → 200 ChannelResponse  (found or created)
                                                   → 400 "You can't start a direct message with yourself."  errors.userId
ChannelResponse += "dmPartnerId": "uuid" | null    (required; the other member, per caller)
GET /api/v1/channels       a dm row only once it has a top-level message (tombstones count)
PATCH|DELETE /channels/{dm} · POST /channels/{dm}/members · DELETE /channels/{dm}/members/{u}
                           → 403 "A direct message can't be renamed, archived or have its members changed."
channel_added → { "channelId": "uuid" }   to user:{ws}:{memberA} and user:{ws}:{memberB}
```

Helpers in each file: `open_dm(client, headers, other_id)` asserting 200, plus the usual `send`.
A third user is module-level `ALAN = uuid.uuid4()` with `tokens.header(user_id=ALAN, name="Alan Turing",
email="alan@collabhub.dev")`. **Every test in these files reaches `open_dm` first; at red that is
`assert 405 == 200`** (the path matches `/{channel_id}`, which has no POST). The column says what
the test checks once it gets past that.

`test_dms.py`:

| Test | Checks (R) |
|---|---|
| `test_opening_twice_either_way_round_is_one_dm` | Ada→Grace, Ada→Grace, Grace→Ada: one id; 2 `channel_members` rows, both `member` (R2, R11 roles) |
| `test_opening_at_once_is_one_dm` | `asyncio.gather` of 5 Ada→Grace and 5 Grace→Ada opens: one id; `SELECT count(*) FROM channels WHERE kind='dm'` is 1 (R2, *Where the rules meet*) |
| `test_the_same_pair_in_another_workspace_is_another_dm` | tokens with `workspace_id=OTHER_WORKSPACE` get a different id |
| `test_a_dm_with_yourself_is_refused_and_nothing_is_written` | 400 detail and `errors.userId`; channel count 0 (R3) |
| `test_any_workspace_role_may_open_a_dm` | Grace's token `roles=("member",)`, Ada's `("admin",)`: both 200 (R4) |
| `test_an_empty_dm_is_not_listed_for_either_member` | after open, neither's `GET /channels` has it, while an empty public channel in the same response is listed; `GET /channels/{dm}` still 200 (R5) |
| `test_a_dm_is_listed_for_both_once_it_has_a_message` | Ada sends: listed for both; Grace `unreadCount` 1, Ada 0 (R5, R6) |
| `test_a_dm_whose_only_message_is_deleted_stays_listed` | Ada deletes it: still listed for both (R5, *Listing and delete*) |
| `test_each_member_sees_the_other_as_partner` | `dmPartnerId` on the open response, on `GET /channels/{id}` and in the list — Grace's id for Ada, Ada's for Grace; `null` on a public channel (R7) |
| `test_a_dm_cannot_be_changed` (parametrized: rename, topic, archive, add member, remove member) | 403 with decision 12's detail — **not** "Only a channel admin can do that." (R9) |
| `test_only_the_author_deletes_in_a_dm` | Grace deleting Ada's message: 403 "Only the author or a channel admin can delete a message."; Ada deleting it: 200 (R8) |
| `test_both_members_can_use_every_message_route` | Grace: history, send, edit own, react, reply in a thread, `GET` the thread, mark read, `GET` members — each 2xx (R8) |
| `test_a_third_user_gets_404_on_every_route` (parametrized over those routes plus `GET /channels/{dm}`, `GET /messages/{id}`, `DELETE /messages/{id}`, `DELETE /messages/{id}/reactions/{emoji}` and `GET /messages/{id}/attachments/{assetId}/download-url` with any asset id — `_visible_message` answers before Asset is asked, `routers/messages.py:429`, so no stub) | 404, detail `"No such channel."` (R11) |

`test_dm_realtime.py`, against `realtime_url` (REST through `httpx.AsyncClient(base_url=url)` as
`test_realtime_writes.py:35-39` does); `hears_nothing` as `test_read_state.py:64-66`:

| Test | Checks (R) |
|---|---|
| `test_a_first_rest_send_announces_the_dm_to_both_members` | Ada (two tabs), Grace, Alan and Ada-in-`OTHER_WORKSPACE` connected, none in the DM room. Ada REST-sends: both Ada tabs and Grace receive `("channel_added", {"channelId": dm})`; then Alan and Ada-elsewhere hear nothing (R10, *Paths* second tab) |
| `test_a_first_socket_send_announces_the_dm` | the same through `send_message` |
| `test_a_first_attachment_only_send_announces_the_dm` | `realtime_url_for(asset_internal_url=…, service_token_url=…)` with `asset_stub`, body `""` and one attachment: Grace receives `channel_added` |
| `test_a_later_message_announces_nothing` | Grace connected and joined to the DM room. Ada's first send: Grace receives `channel_added` (asserted — the positive, so a build that never emits fails here). Ada's second send: Grace receives `message_received`, then hears nothing |
| `test_a_first_message_announces_a_dm_and_not_a_channel` | Grace joined to a public channel and connected. Ada's first send into the DM: Grace receives `channel_added` for the DM. Ada's first send into the public channel: Grace receives its `message_received`, then hears nothing — the DM check, not "first", is what emits |
| `test_two_first_messages_at_once_announce_the_dm_at_least_once` | Ada and Grace REST-send at once: Grace receives ≥1 `channel_added`; both messages stored |
| `test_a_third_user_cannot_use_a_dm_over_the_socket` (parametrized: `join_channel`, `send_message`, `edit_message` and `delete_message` on Ada's message, `mark_read`) | Alan's ack is `ok: false`, status 404, detail "No such channel."; Ada's message is unchanged after (R11) |
| `test_typing_in_a_dm_reaches_the_other_member` | Grace joined; Ada's `typing` reaches her as `user_typing` (R8) |

Modify `test_search.py`: `test_a_dm_is_searchable_by_its_members_only` — Ada and Grace's DM, Ada's
"the launch date" indexed; a public channel exists so Alan's search filters rather than returning
early (`test_search.py:117-118`); Grace finds it, Alan gets `[]` (R11).

Modify `test_schema.py`: `test_the_dm_pair_index_is_unique_and_partial_on_kind_dm` — from
`pg_indexes`, `ux_channels_dm_pair` is `UNIQUE` on `(workspace_id, name)` `WHERE (kind = 'dm'::text)`.
Red: the index row is missing (`assert None is not None` or the test's own message).

Leave uncommitted.

## Task 3: The journey and the SPA's red (RED)

**Files:** `tests/bdd/features/direct_messages.feature`, `steps/test_dm_steps.py`,
`pages/chat_page.py`; the Vitest files in the file map.

```gherkin
@bdd
Feature: Direct messages

  Any two people in a workspace can talk privately. The + beside Direct messages in the
  sidebar lists everyone else in the workspace; picking someone opens the conversation the
  two of you share, and it is named after them. It shows up in both sidebars as soon as
  something is said in it, with the same unread count a channel has.

  Background:
    Given Ada is signed in

  Scenario: Grace sees the direct message Ada starts, and replies
    Given Ada has created a public channel named "general"
    And Grace is looking at the "general" channel
    When Ada starts a direct message with Grace
    And Ada sends "hi"
    Then Ada appears in Grace's direct messages with 1 unread message without reloading
    When Grace opens her direct message with Ada
    Then Grace sees "hi" in the channel
    When Grace sends "hello back"
    Then Ada sees "hello back" in the channel without reloading
```

- Reused verbatim: `Given Ada is signed in`, `Given Ada has created a public channel named`,
  `Given Grace is looking at the "{name}" channel`, `When Ada sends "{body}"`,
  `Then Grace sees "{body}" in the channel` (`steps/conftest.py`).
- New, in `test_dm_steps.py`: `When Ada starts a direct message with Grace` →
  `ada.start_dm(GRACE_NAME)`; `Then Ada appears in Grace's direct messages with {count:d} unread
  message without reloading` → `grace.has_dm_unread_badge(ADA_NAME, count)`; `When Grace opens her
  direct message with Ada` → `grace.open_dm(ADA_NAME)`; `When Grace sends "{body}"` (`parsers.re`,
  as `conftest.py:143`) → `grace.send_message_and_wait`; `Then Ada sees "{body}" in the channel
  without reloading` → `ada.wait_for_message`. Names from `ADA_NAME`/`GRACE_NAME` ("ada", "grace").
- `ChatPage` gains `start_dm(name)` (click `dm-new`, click `[data-testid='dm-pick'][data-member-name=…]`,
  wait for `channel-view[data-channel-name=…]`, then `wait_for_channel_joined()`), `open_dm(name)`
  (click `[data-testid='dm-list-item'][data-dm-name=…]`, wait for the view), and
  `has_dm_unread_badge(name, count)` (`_settle()`, then a retrying `expect` on the item's
  `channel-unread-badge` `data-count`). Selectors only there.
- The markup Task 6 must render to match: `dm-new` on the **+**, `dm-pick` + `data-member-name` per
  picker entry, `dm-list-item` + `data-dm-name` per row, `channel-unread-badge` inside the row, and
  `channel-view`'s `data-channel-name` set to `channelLabel` — **bare, no `#`**: `general` for a
  channel, exactly as today, and the partner's display name for a DM (decision 18). DM rows are not
  `channel-list-item`s, so `channel_names()` and `has_channel` see channels only.
- Expected red: the steps bind (`--generate-missing` prints nothing) and collection passes; the
  scenario cannot run before the code-writer (it needs the stack).

**Vitest** — expected red is a load failure for the new modules, and an assertion for the modified
files (whose components exist).

**SPA interfaces** — what Task 6 builds and these tests render:

| Unit | Interface |
|---|---|
| `features/channels/directMessages.ts` | `isDm(channel: Channel): boolean` · `channelLabel(channel, nameFor: (id: string) => string): string` — `channel.name`, or `nameFor(channel.dmPartnerId)` for a DM · `channelTitle(channel, nameFor): string` — `` `#${channel.name}` ``, or the DM's label · `sortedDms(channels: Channel[], nameFor): Channel[]` — the DMs only, by label with `localeCompare` |
| `DirectMessageList` (new) | `{ accessToken: string; workspaceId: string \| null; userId: string }`. Reads `useChannels` and `useWorkspaceMembers` itself |
| `ChannelList` | props unchanged; renders `channels.filter((c) => !isDm(c))` in server order and **does not read the directory**; its empty state counts those |
| `ChannelHeader` | gains a **required** `label: string`; renders the aria-hidden `#` only when `!isDm(channel)`; no topic, no controls for a DM whatever `myRole` says |
| `ChannelView` | calls `useWorkspaceMembers`; passes `label={channelLabel(…)}` to the header and `data-channel-name`, `channelTitle={channelTitle(…)}` to the composer; no `MemberPanel` for a DM |
| `MessageComposer` | prop `channelName` → `channelTitle: string`; `aria-label` and placeholder `` `Message ${channelTitle}` `` — so `"Message #general"` is unchanged for a channel |
| `useChannelNames` | gains `nameFor`; returns `(id) => string \| null` **titles** |
| `SearchResult` | prop `channelName` → `channelTitle: string \| null`; renders `channelTitle ?? '#…'` |

`directMessages.test.ts`. Tests: a channel's label is its bare name (`general`, no `#`) and its title
`#general`; a DM's label and title are both the partner's name; a partner missing from the directory
labels as `shortId`; `sortedDms` returns only DMs, by name, when the server order is the reverse (and
ids sort a third way, so neither reading passes by accident). Red: `Failed to resolve import
"./directMessages"`.

`DirectMessageList.test.tsx` — MSW for `GET /api/v1/channels` and `auth.members`. Red: `Failed to
resolve import "./DirectMessageList"`.
- the section is a region named "Direct messages" listing only the `kind: 'dm'` rows of a mixed
  response, each a link named after the partner, in name order (R6, R7);
- a DM with unread messages shows the badge (`aria-label` from `badgeLabel`) and a bold name; the one
  in `readingChannelId` shows none (R6);
- the **+** (button named "New direct message") opens a list of members by display name, without the
  caller (`userId`), sorted by name (R1, decision 17);
- picking Grace `POST`s `{ userId: GRACE }` to `/api/v1/channels/dm` and navigates to `/c/<id>` of
  the response (R1);
- a held `POST`, then a `rerender` with another `workspaceId`, then the release: the location stays
  where it was — and the same test without the switch navigates (decision 19, *Paths*).

`useChannelSocket.dm.test.tsx` (pattern of `useChannelSocket.threads.test.tsx`). Red: assertions
fail (no `channel_added` listener; `serverEmit` reaches nothing):
- `channel_added` with a cached list starts a new `GET /api/v1/channels`, and the DM lands in the
  cache (R10);
- a poll in flight (held reply without the DM) when the event arrives: release the old fetch
  **before** the new one, and in a second test **after** it — the cache ends with the DM both ways
  (issue *Timing*);
- the first load in flight, no data yet: after it resolves (without the DM) a further `GET` is made
  and the DM lands (decision 16). Count `requests()` to `/api/v1/channels`.

Modify `ChannelHeader.test.tsx`: `renderHeader(channel, label = channel.name)` passes `label`. A DM
rendered with `label="Grace Hopper"` has a heading whose text content is exactly `Grace Hopper` (the
`#` is `aria-hidden`, so the accessible name can't tell — read `textContent`) and no topic; a public
channel's heading text is still `# general`; a DM with `myRole: 'admin'` (a
fixture no server sends, to flip kind alone) shows no Rename or Archive, while the same role on a
public channel does (R9). Red: the header ignores the extra prop and shows `# dm:…`; Rename is found.
Modify `ChannelList.test.tsx`: a mixed response lists the channels and no DM row (R6) — red, the DM
is listed by its stored name; `:50` passes `label="random"` (Task 6, ripple).
Modify `ChannelView.test.tsx`: for a DM, no "Members" heading, the composer's placeholder is
`Message <name>`, and the thread panel still opens; a public channel still shows "Members" (R9, R7).
Red: "Members" is found. (`ChannelView.test.tsx:109` already stubs `auth.members`, so the view
reading the directory adds no stub.) Modify `SearchPage.test.tsx`: a result in a DM shows the partner's name and
no `#`; a channel result still shows `#general` (R7). Red: the result shows `#dm:…`.
Modify `test/factories.ts`: `aChannel()` gains `dmPartnerId: null`.

Leave uncommitted.

## Task 4: The pair index, the rules and the listing (GREEN)

**Files:** `models.py`, `alembic/versions/0007_dm_pair.py`, `dms.py`, `channels.py`

```python
# 0007_dm_pair.py — the index is the uniqueness of a pair; get-or-create's ON CONFLICT names it.
op.create_index(
    "ux_channels_dm_pair", "channels", ["workspace_id", "name"],
    unique=True, postgresql_where=sa.text("kind = 'dm'"),
)
```

```python
# dms.open_dm — the insert. index_where must match the partial index or Postgres can't infer it.
stmt = (
    pg_insert(Channel)
    .values(id=uuid7(), workspace_id=workspace_id, name=pair_name(user_id, other_id),
            kind=DM, created_by=user_id)
    .on_conflict_do_nothing(index_elements=["workspace_id", "name"], index_where=text("kind = 'dm'"))
    .returning(Channel.id)
)
```

- [ ] The same `Index` in `Channel.__table_args__`; migration `0007`, `down_revision = "0006"`.
- [ ] `dms.py` to Task 1's interface. `open_dm(session, *, workspace_id, user_id, other_id) ->
  uuid.UUID`: `pair_name` first (so a self-DM writes nothing), the insert above, then two `MEMBER`
  rows if a row came back, else `SELECT id … WHERE workspace_id, kind = 'dm', name`. No commit.
- [ ] `opens_dm(session, channel: Channel, *, thread_root_id: uuid.UUID | None) -> bool`: `kind == DM`,
  `thread_root_id is None`, and no `messages` row with that `channel_id` and `thread_root_id IS NULL`
  (deleted ones count). Called **before** insert (decision 15).
- [ ] `channels._visible_from(row, user_id)` sets `dm_partner_id=dms.partner_of(row[0], user_id)`;
  `list_page` and `get_visible` pass the caller.
- [ ] `channels.list_page` only: `or_(Channel.kind != DM, exists(select(Message.id).where(
  Message.channel_id == Channel.id, Message.thread_root_id.is_(None))))`. Not in `_visible_query`:
  an empty DM stays reachable by URL and to `join_channel`.
- [ ] Task 1: 8 passed. `test_schema.py`'s new test passes. Leave uncommitted.

## Task 5: The route, the guards and `channel_added` (GREEN)

- [ ] `schemas.OpenDmRequest(CamelRequest)`: `user_id: uuid.UUID`. `ChannelResponse.dm_partner_id:
  uuid.UUID | None` with no default, filled in `_as_channel` from `visible.dm_partner_id`.
- [ ] `POST /dm` in `routers/channels.py`, beside `create_channel` (no route on `/{channel_id}` takes
  a POST, so order does not matter). `SelfDmError` → decision 13's 400.
  Commit, then `_visible_or_404(…, with_read_state=True)` for the body. `require_user`.
- [ ] `dms.check_manageable(visible.channel)` → `ProblemException.forbidden(<decision 12>)` in
  `update_channel`, `archive_channel`, `add_member`, `remove_member`, between `_visible_or_404` and
  `_admin_or_403`.
- [ ] `realtime.publish_channel_added(sio, *, workspace_id, channel_id, user_ids)`: one `emit` of
  `{"channelId": str(channel_id)}` per `reader_room(workspace_id, uid)`; no-op when `sio is None`.
- [ ] REST `send_message` (`routers/messages.py:292`): keep `_visible_channel`'s return; `first =
  await dms.opens_dm(session, visible.channel, thread_root_id=root_id)` after the body check and before
  `messages.create`; after `publish_message_received`, `if first:` publish to `dms.pair_of(...)`.
- [ ] Socket: `authorized_channel` returns the `VisibleChannel` (`typing` ignores it); `send_message`
  does the same as REST, inside its session, publishing after `publish_message_received`.
- [ ] Regenerate: `python -m messaging.openapi > src/frontend/openapi/messaging.json`, then
  `npm run generate:api`. Task 2 passes. Messaging integration: 276 + Task 2's or more.
- [ ] Leave uncommitted.

## Task 6: The SPA (GREEN)

- [ ] `openDirectMessage(accessToken, userId): Promise<Channel>` in `lib/api/messaging.ts`.
- [ ] `useOpenDirectMessage(accessToken, workspaceId)` in `useChannels.ts`: `mutationFn` takes
  `{ userId, workspaceId }`; `onSuccess` invalidates `channelKeys.list(variables.workspaceId)` and
  returns the channel; the component navigates only if `variables.workspaceId` equals the current
  one (a ref), per decision 19.
- [ ] `directMessages.ts` to Task 3's interface. `DirectMessageList.tsx`: `<section
  aria-labelledby>` headed "Direct messages", the **+** button, the picker (`useWorkspaceMembers`,
  minus `userId`, sorted), rows as `NavLink`s with the badge and bold rule from `ChannelList`
  (share it — extract the badge if that keeps both readable).
- [ ] `ChannelList` renders the non-DM rows only (`!isDm`), with no directory, and its empty state
  counts those. `ChatLayout` mounts `DirectMessageList` below it in the `<nav>`, passing
  `current.profile.id`; `DirectMessageList` sorts with `sortedDms`.
- [ ] `ChannelView` reads `useWorkspaceMembers`; `label = channelLabel(channel, directory.nameFor)`
  goes to `data-channel-name` and `<ChannelHeader label={label}>`; `channelTitle(…)` goes to
  `<MessageComposer channelTitle>`; no `MemberPanel` for a DM. `ChannelHeader` per Task 3's table.
- [ ] `useChannelNames(accessToken, workspaceId, ids, nameFor)` returns titles; `SearchResult`'s
  prop becomes `channelTitle: string | null`, rendered as `channelTitle ?? '#…'`.
- [ ] `useChannelSocket`: `live.on('channel_added', …)` invalidates `channelKeys.list(workspaceId)`;
  if `getQueryData` is undefined and `isFetching` > 0, `reapplyAfterFetch` the invalidation.
- [ ] Ripple: `MessageComposer.test.tsx:40` and `MessageComposer.attachments.test.tsx:37` render
  with `channelTitle="#general"`, `:256` with `` channelTitle={`#${channelId}`} `` — their
  `Message #…` queries stay as they are; `ChatLayout.test.tsx`, `ChatLayout.attachments.test.tsx`,
  `App.test.tsx`'s signed-in test at `:93` and `CreateChannelDialog.test.tsx`'s `ChatLayout` render
  add `auth.members([...])`; `ChannelList.test.tsx:50` passes `label="random"`.
- [ ] Task 3's Vitest passes; `npm --prefix src/frontend run typecheck` clean. Leave uncommitted.

## Task 7: The record

- [ ] Register: D8b → 🟢 "Built 2026-10-05" with the pair key, listing rule and `channel_added`;
  new **D44** 🟡 (decision 20), naming `channels.add_member`'s docstring and `dms.open_dm`.
- [ ] ADR `docs/adr/261005-direct-messages-are-dm-channels.md` with the `adr-writer` skill:
  `kind='dm'`, one per pair by the name key and partial index, listed on first message,
  `channel_added`, no admin.
- [ ] Doc 02: the route in §3.1's table; §3.1.1 the listing rule and R9's 403; §3.1.2 line 185-187
  (DMs open through `POST /channels/dm`); §3.1.3 `dmPartnerId`; §3.2 `channel_added`; §4 the index;
  §9 line 1014 settled.
- [ ] Doc 06: §3 nothing; §5.2 the *Direct messages* section, picker, naming, `channel_added`
  handling and decision 16; §5.4 a DM result's label.
- [ ] Vocabulary §34: the five new phrases.
- [ ] Sweep: docstrings in `test_channel_rules.py:96`, `test_channels.py:170`; comments at
  `models.py:60-61`, `CreateChannelDialog.tsx:56`; `grep -rn "D8b\|kind='dm'" src docs/design`.

## Task 8: Verification

- [ ] `scripts/test.sh lint unit integration`, then `scripts/test.sh e2e` — each once; the e2e layer
  is the journey's first run (`-- -k direct` only to iterate on a failure). Counts at or above the
  baseline.
- [ ] `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)` and
  `.claude/hooks/security.sh`. The `ON CONFLICT` is built by SQLAlchemy, not interpolated (CH006).
- [ ] **First real run** on Compose, with the issue's *Acceptance* list: three browsers (Ada, Grace,
  Alan); an empty DM unlisted for both; "hi" appears for Grace and in Ada's second tab; Grace's **+**
  lands in the same DM; Alan's URL and search find nothing; each header names the other person.
  Expect it to find something the tests did not; fix it with a test and record it below.
- [ ] If a sibling branch merged while this was in flight, merge `main` and rerun all of the above.
- [ ] Fill in *Found while building*. Leave the worktree dirty and report.

## Found while building

Round 1, code-writer (the build is done; verification is held for a send-back — see
`reviews/code-writer-sendback-3.md`):

- **R9 guard lives in `_admin_or_403`, not beside each call.** `_manageable_or_403` (the DM refusal
  with decision 12's wording) runs first inside `_admin_or_403`, which only the four management
  routes call (rename, archive, add member, remove member). Same order as the plan (after the 404,
  before the role test) with no way to forget one route. Pinned by `test_a_dm_cannot_be_changed`.
- **`useOpenDirectMessage(accessToken)`** takes only the token; the workspace travels in the mutation
  variables (`{ userId, workspaceId }`), as the plan's `onSuccess` needs. Pinned by
  `DirectMessageList.test.tsx`'s workspace-switch tests.
- **`UnreadBadge.tsx` extracted** (the plan said "share it — extract the badge"); `ChannelList` and
  `DirectMessageList` both use it. No test of its own: it is covered through both lists.
- **`messaging.json` was edited by hand**, then `npm run generate:api`, because the sandbox refused
  `python -m messaging.openapi > file`. The edits follow the generator's key order; **the human should
  regenerate once** (`python -m messaging.openapi > src/frontend/openapi/messaging.json`) and expect no diff.
- **Four test faults and the unmade ripple edits** went back to the test pair: three Python tests that
  no correct build can pass (history read before the send; `thread_summary_changed` is a legitimate
  event after a reply; `varchar` renders `(kind)::text`), and the Task 6 ripple edits to existing
  Vitest files. See the send-back file.

Round 2, code-writer (after the test pair's fixes to send-back 3): the ripple edits and the three
Python test faults were repaired in the tests; everything now passes, including the journey
`direct_messages.feature` on its first e2e run (24 scenarios, 0 failed). The run found nothing the
tests had missed, so no further departure. The send-back round trip is pinned by the corrected tests
named in `reviews/code-writer-sendback-3.md`. The by-hand three-browser run is left for the human.

## Not in this plan

- Everything in the issue's *Not in this issue*: group DMs, a "Message" button on a member, ordering
  by activity, hiding a DM, checking the other user with Auth, anything on workspace removal.
- The sidebar reads one page of `GET /channels` (50); with DMs in the same list a large workspace
  can push rows off it. Paging the sidebar is its own change.

## Self-review

- **Issue coverage:** R1 → Tasks 2, 3, 5, 6 · R2 → 1, 2, 4 · R3 → 1, 2, 5 · R4 → 2 · R5 → 2, 4 ·
  R6 → 3, 6 · R7 → 1, 2, 3, 6 · R8 → 2, 4 · R9 → 1, 2, 3, 5, 6 · R10 → 2, 3, 5, 6 · R11 → 2.
  *Where the rules meet*: concurrency → `test_opening_at_once_is_one_dm`; listing and delete →
  `…only_message_is_deleted_stays_listed`; listing and unread → `…listed_for_both_once…`; two
  first messages → `…at_least_once`; event and poll → the two race-order Vitest tests and the
  first-load one; naming and the directory → `directMessages.test.ts` `shortId`; delete and no admin
  → `test_only_the_author_deletes_in_a_dm` and the remove-member case of `test_a_dm_cannot_be_changed`.
  *Paths*: first load and reconnect (existing `useChannelSocket.test.tsx:356`) · not looking →
  realtime REST test · second tab → same · workspace switch → `DirectMessageList` test · empty then
  leave → `test_an_empty_dm…` and `test_opening_twice…` · search result → `SearchPage.test.tsx` ·
  third user → the 404 tests.
- **Interfaces to tests:** `pair_name`, `pair_of`, `partner_of`, `check_manageable` → `test_dms.py`;
  `dm_partner_id` → `test_dm_dto.py`; `open_dm` → `test_opening_*`; `opens_dm` and
  `publish_channel_added` → `test_dm_realtime.py`'s first-send and announces-nothing tests;
  `openDirectMessage` and `useOpenDirectMessage` → `DirectMessageList.test.tsx`; `isDm`,
  `channelLabel`, `channelTitle`, `sortedDms` → `directMessages.test.ts`; `ChannelHeader`'s `label`
  → `ChannelHeader.test.tsx`; `ChannelList`'s filter → `ChannelList.test.tsx`; `channelTitle` on the
  composer and search → `ChannelView.test.tsx`, `SearchPage.test.tsx`; the `channel_added` handler →
  `useChannelSocket.dm.test.tsx`. A channel's `data-channel-name` staying bare is pinned by
  `channelLabel`'s unit test and by the 23 existing scenarios in Task 8's e2e run.
- **Names:** `channel_added`, `dmPartnerId`, `/api/v1/channels/dm`, `ux_channels_dm_pair` everywhere.
- **Known ripple:** composer prop rename, `auth.members` stubs in four `ChatLayout` renders, and
  `ChannelHeader`'s `label` (Task 6).

## Review responses

Round 1 (`reviews/plan-reviewer-1.md`):

1. **Fixed.** Decision 18 now has two helpers: `channelLabel` is bare (`general`), `channelTitle`
   carries the `#`. `data-channel-name` = `channelLabel`, so every existing page-object lookup
   still matches; the composer's `Message #general` is unchanged (Task 3 SPA interfaces, Task 6).
2. **Fixed.** Task 3's *SPA interfaces* table: `ChannelHeader` takes a required `label` prop from
   `ChannelView`; `ChannelList` filters with `isDm` and never reads the directory; DM sorting is
   `sortedDms` in `DirectMessageList`, which reads `useWorkspaceMembers` itself. `splitChannels` is
   gone.
3. **Fixed.** File map and Task 6 ripple add `App.test.tsx` (`:93`), `CreateChannelDialog.test.tsx`
   (`:103-110`) and `ChannelList.test.tsx:50` (the new `label` prop). `ChannelList`'s six other
   renders are unaffected, since it reads no directory; `ChannelView.test.tsx:109` already stubs one.
4. **Fixed.** `test_a_first_message_in_a_channel_announces_nothing` is now
   `test_a_first_message_announces_a_dm_and_not_a_channel`, with the DM's `channel_added` asserted in
   the same test; `test_a_later_message_announces_nothing` asserts the first send's `channel_added`
   before the second send.
5. **Fixed.** The REST 404 list adds `DELETE /messages/{id}`, `DELETE …/reactions/{emoji}` and
   `download-url` (404 before Asset is called, `routers/messages.py:429`); the socket test is
   parametrized over `join_channel`, `send_message`, `edit_message`, `delete_message`, `mark_read`.
6. **Fixed.** Task 8 has the sibling-merge step.
