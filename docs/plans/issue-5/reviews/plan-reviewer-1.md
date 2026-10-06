# Plan review — issue 5, round 1: changes_requested

A strong plan. The backend design holds up: the pair key, `ON CONFLICT`, first-send detection
before insert, and the listing rule in `list_page` only all work, and every issue requirement has a
test. It goes back for four majors, all on the SPA and red-gate side: (1) a markup change that
would break every existing BDD scenario that opens or creates a channel; (2) a header interface the
RED tests would have to guess; (3) two test files the change breaks that the file map doesn't name;
and (4) a guard test that would pass at red.

## Expectations

Written from the issue, doc 02 §3.1–§3.2/§4, doc 06, register D8b/D18/D28/D31 and the code
(`channels.py`, `routers/channels.py`, `models.py`, `messages.py`, `realtime_writes.py`,
`routers/messages.py`, `ChannelList.tsx`, `useChannels.ts`, `useChannelSocket.ts`,
`useChannelNames.ts`, `SearchResult.tsx`, `ChannelView.tsx`, TanStack query-core 5.101.4) —
before the plan was opened.

### Decisions
- **Pair key (R2):** how is "one DM per pair, either order" made unique in the database —
  a canonical ordered pair column/index, a derived `name`, a separate table? Does it hold
  under two concurrent first opens (unique-violation → re-read, or `ON CONFLICT`)? Is the
  uniqueness per workspace?
- **Route shape and status:** what route opens/creates the DM; 200 vs 201 for found vs
  created; what body (`userId`)?
- **Stored `name`:** what goes in the `NOT NULL` column, and does it bypass
  `validate_name`? Since `GET /channels` sorts and pages on `(name, id)` and the SPA reads
  only the first page, does the chosen value decide which DMs fall off page one?
- **DM membership rows:** both members' role — `member` (so no admin, R8/R9) or anything
  else? `created_by` = the opener?
- **R3 refusal:** what status and `detail` does a self-DM get (400 `validation-error`
  under `errors.userId`?), and is it refused before anything is written?
- **R5 listing rule:** where does "has at least one top-level message, tombstones
  included" apply — `list_page` only, leaving `get_visible`/`join_channel`/send/typing able
  to reach an empty DM (R5 "reachable … through its URL")? Does "top-level" exclude a reply?
- **R7 DTO field:** its name, and is it required-nullable in OpenAPI (generated types)?
  Computed how — a join on `channel_members` for the other row — and what for a DM where
  the caller's row is the only one?
- **R9 refusals:** what does rename/topic/archive/add/remove answer for a DM — today's
  403 "Only a channel admin can do that." via a null role, or a DM-specific 400/409/403
  with its own `detail`? Which check comes first, visibility (404 for a third user)?
- **"Live arrival" first-send test (R10):** how is "first top-level message" detected —
  inside the send transaction before commit (each concurrent send sees itself first → at
  least once), or after commit (both see two → **neither** emits)? Shared by REST, socket
  and attachment-only paths?
- **`channel_added` handler (R10 / Timing):** `invalidateQueries` (cancelRefetch default
  true) — and what of an event arriving **before the list's first load completes**, when
  TanStack reuses the in-flight fetch? Is the event also emitted when the sender's own
  connection receives it (second tab)?
- **Picker UI (R1):** workspace members from `useWorkspaceMembers`, minus the caller; the
  get-or-create mutation keyed by workspace so a switch mid-flight can't navigate/put the
  old DM in the new sidebar.
- **Naming (R7):** one helper for "display name of a channel" used by sidebar, header,
  composer placeholder, search result and `useChannelNames`? Fallback to `nameFor`'s
  `shortId`? What do `data-channel-name` attributes carry for a DM?

### Conflicts
- R8 "exactly as in a private channel" vs R8/R9 "a DM has no admin": a private channel's
  admin can delete others' messages; a DM can't. Does the plan state that the DM's
  difference is only the absent admin row?
- R5 "listed once it has a message" vs §3.1.1 "membership gates the messages, not the
  knowledge it exists" / `GET /channels` = "any kind the caller is a member of": doc 02
  must be changed, not contradicted silently.
- R7 "stored `name` never shown" vs `ChannelView`/`ChannelList` `data-channel-name` and the
  BDD page objects that find a channel by its name.
- R9 "topic refused" vs doc 02's PATCH semantics (topic is part of PATCH).
- Decided already 5 (userId unchecked) vs R4/R1 — needs a register entry, not a fix.
- `validate_kind`/`CREATABLE_KINDS` tests pinned to refusing `dm` — `POST /channels` must
  still refuse `kind=dm` (or does it?).

### Tests
- Integration: get-or-create both orders → same id; concurrent opens (two sessions, a
  real race, not sequential); self → refused and `count_in_workspace` unchanged; any
  workspace role (a token with `member` role only).
- Integration: listing — empty DM absent for both, live DM present for both, tombstoned
  DM present; a reply alone? (impossible without a root — fine); a third user's list.
- DTO: other member's id for each side; null on public and private.
- 404 for a third user on GET channel, history, send (REST & socket), members,
  `join_channel`, typing, read marker, message GET/thread/reactions/download-url; search
  returning no DM hit for the third user, a hit for a member (positive in the same test).
- Every management route refused on a DM, with the status/detail, and the positive case
  on a private channel so the test isn't green by visibility.
- Author-only delete: the other member gets refused (403), the author succeeds.
- `channel_added`: REST, socket, attachment-only first sends each reach both personal
  rooms; a second message emits nothing (positive anchored); a non-DM first message emits
  nothing; a third user's room gets nothing.
- Vitest: section split and sort by display name (two DMs whose stored-name order differs
  from display-name order), unread badge/bold, naming in four places with `shortId`
  fallback, no `#`, hidden controls and member panel, picker excludes caller,
  `channel_added` invalidates the list (and the early-arrival case), workspace switch.
- BDD: the journey; last step shows server state (Ada sees Grace's reply live — a second
  user, so it proves the server).

### Risks
- **Race between two openers** — unique-index violation handling must not leave a
  half-written channel (the membership rows inserted with the channel in one flush).
- **First-send detection after commit** loses the event entirely under concurrency.
- **`channel_added` before the first list load** — reused in-flight fetch predates the
  message (issue's own assumption), list stays stale until the next 30 s poll.
- **Search naming:** `useChannelNames` returns `channel.name` — would show the stored name.
- **Page one of `GET /channels`:** DMs interleaved by stored name with channels; >50 rows
  hides some (existing limit, amplified).
- **Delete gating in the SPA** uses `myRole`; DM rows with `admin` would show delete on the
  other's messages.
- **Existing tests that pin the `dm` refusal** (`test_channel_rules.py`,
  `test_channels.py`) — what becomes of them.
- **OpenAPI regen** and MSW stubs/factories (`aChannel()`) needing the new required field.

## Coverage

| Issue item or expectation | Plan | Outcome |
|---|---|---|
| R1 + picker of members minus caller, navigate to `/c/{id}`, create if none | D9, D17, Task 3 `DirectMessageList` tests, Task 6 | covered |
| R2 one per pair, either order, same instant | D7/D8, `test_opening_twice…`, `test_opening_at_once…`, schema test | covered |
| R3 self refused, nothing created | D13, unit + `…refused_and_nothing_is_written` | covered |
| R4 any role | `test_any_workspace_role…` (`mint` takes `roles`, checked) | covered |
| R5 listed once a top-level message exists, tombstone counts, empty reachable by URL | D3, Task 4 `exists` in `list_page` only, three listing tests | covered |
| R6 own section, below channels, sort by name, same badge/bold | Vitest helper + `DirectMessageList` tests | covered |
| R7 partner id on DTO; sidebar, header, placeholder, search show name, no `#`; stored name never shown | D10, D18; unit/integration DTO; Vitest four surfaces | **misread in markup** (finding 1); header interface missing (finding 2) |
| R8 works like private; author-only delete | D11, `test_both_members…`, `test_only_the_author…`, typing test | covered (minor gaps, finding 5) |
| R9 management refused; SPA hides controls and member panel | D12, parametrized 403 test, header/view Vitest | covered |
| R10 `channel_added` to both rooms on all three first-send paths; SPA refetches | D15, D16, `test_dm_realtime.py`, `useChannelSocket.dm.test.tsx` | covered, one guard green at red (finding 4) |
| R11 404 for anyone else on REST, socket; no search hits | parametrized 404, socket join/send, search test | covered (minor gaps, finding 5) |
| Decided 1–6 | Decisions 1–6 | covered |
| Tests section (pytest/Vitest list; one journey) | Test approach table, Task 3 Gherkin | covered |
| Record (D8b 🟢, new entry, doc 02, doc 06, ADR) | Task 7, D20 (D44 is the next free id, checked) | covered |
| Not in this issue | *Not in this plan* | covered |
| Conflict: R8 "as private" vs no admin | D11 | settled |
| Conflict: R5 vs doc 02 §3.1.1 list rule | Task 7 §3.1.1 | settled |
| Conflict: "they change with this issue" vs keeping `kind=dm` refusal | D14 **assumed**, *Corrections* | settled |
| Conflict: stored name never shown vs `data-channel-name` | Task 3/6 `data-channel-name={label}` | misread (finding 1) |
| Exp: pair key, route, status, stored name, roles | D7–D11 | settled |
| Exp: first-send detection before vs after commit | D15 (I traced the interleavings: none-emits is impossible) | settled |
| Exp: `channel_added` before the first list load | D16, verified against query-core 5.101.4 `query.ts:411-419` | settled |
| Exp: workspace switch mid get-or-create | D19 + Vitest | settled |
| Exp: search naming via `useChannelNames` | Task 6 returns labels | settled |
| Exp: first page of 50 | *What no test covers*, *Not in this plan* | settled (declared) |
| Exp: ripple — callers of changed props/hooks | file map ripple row | partly missing (finding 3) |

## Findings

### 1. `channel-view`'s `data-channel-name` becomes `#general` for every channel — major
**Where:** D18 (`channelLabel` → `"#general"`), Task 3 markup bullet, Task 6 ChannelView bullet ·
**Checked:** `tests/bdd/pages/chat_page.py:125` and `:208` (`_view_of`, `open_channel`) locate
`[data-testid='channel-view'][data-channel-name='{name}']` with the bare name. Every existing scenario
that creates or opens a channel goes through them (23 in `docs/test-report.md`).
Task 6 sets `data-channel-name={label}`, and the plan's `label` for a channel includes the `#`. Every
one of those waits would time out, and the only place it would show up is the code-writer's e2e run.
Task 3's "(the display name for a DM)" suggests the intent is the bare name for a channel, but the
interface says otherwise. Settle it in the plan: either the attribute carries the name without `#`
for a channel and the display name for a DM, or `channelLabel` has no `#` and the `#` is
presentation. The composer's `aria-label` (`Message #general`, queried by the existing composer
tests) must come out the same either way.

### 2. How the header gets a DM's name is not specified — major
**Where:** Task 3 "Modify `ChannelHeader.test.tsx`", Task 6 "ChannelHeader shows the label" ·
**Checked:** `ChannelHeader.tsx` takes `{accessToken, workspaceId, channel}` and renders
`channel.name` after an `aria-hidden` `#`. `ChannelView` computes `label` but the plan never says
it is passed down.
The RED header test has to render a DM "showing the partner's name". To do that it either passes a
new prop (which one?) or stubs `auth.members` so the header can resolve the name itself. The
test-writer would have to guess, and the code-writer could guess differently. The same question
applies to `ChannelList`: `splitChannels(channels, nameFor)` needs a directory, so does
`ChannelList` now call `useWorkspaceMembers`, or does it filter with `isDm` and leave sorting to the
DM section? Name the prop or the hook for each, in *Interfaces*.

### 3. Ripple: two more test files render `ChatLayout` with no directory stub — major
**Where:** file map, ripple row · **Checked:** `App.test.tsx:93-101` ("sends a signed-in visitor…
into the app") and `CreateChannelDialog.test.tsx:103-110` render the whole `ChatLayout`. Neither
stubs `auth.members`, and `setup.ts:32` is `onUnhandledRequest: 'error'`.
The plan adds `auth.members` to `ChatLayout.test.tsx` and `ChatLayout.attachments.test.tsx`, for
exactly the reason that applies to these two: `DirectMessageList` loads the directory on mount.
Add both files, and whatever finding 2's answer adds: `ChannelList.test.tsx` (six renders, plus
`ChannelHeader` at `:50`) if either component starts reading the directory or takes a new required
prop.

### 4. `test_a_first_message_in_a_channel_announces_nothing` passes at red — major
**Where:** Task 2, `test_dm_realtime.py` table, and the claim "every test in these files reaches
`open_dm` first" · **Checked:** as written, the test needs a public channel and no DM. Today nothing
emits `channel_added`, so "`message_received`, then nothing" holds at the red gate and proves nothing.
Give it its positive in the same test: the first message in a DM announces it, and the first message
in a public channel announces nothing. That also makes the 405 claim true. Do the same for
`test_a_later_message_announces_nothing`: assert the first send's `channel_added` before the second
send. Otherwise a build that never emits passes it once it is past red.

### 5. Third-user and member coverage leaves a few routes out — minor
**Where:** `test_a_third_user_gets_404_on_every_route`, `test_both_members_can_use_every_message_route`
· **Checked:** routes in doc 02 §3.1 and the socket handlers in `realtime_writes.py`.
Two kinds of route are left out:
- From the parametrized lists: attachment `download-url`, `DELETE /messages/{id}` and
  `DELETE …/reactions/{emoji}`.
- On the socket: `edit_message`, `delete_message` and `mark_read`. R11 says "every REST route and
  socket event".

They share `_visible`/`get_visible` with private channels, so the risk is low. Add them to the
parametrize lists, or say why not.

### 6. Task 8 lacks the sibling-merge step — minor
**Where:** Task 8 · **Checked:** exemplar Task 8, "If a sibling branch merged while this was in
flight, merge `main` and rerun". The issue says no sibling is unmerged today, but one could merge
while this is in flight.

## Left for later stages
- Finding 5, if the writer prefers to leave it out.
- **Test pair:** `test/api.ts`'s `messaging.post` stub always answers **201**. The DM route answers
  200. That is harmless to `openapi-fetch` and to the types (`SuccessBody` accepts 200 | 201), but a
  test that asserts on the status would need its own handler.
- **Human:** D14 (`POST /channels` still refuses `kind=dm`) and D17 (picker sorted by name) are
  **assumed**. Both are defensible and cheap to change.
- **Human:** the sidebar reads one 50-row page of `GET /channels`, and DMs (stored as `dm:…`) now
  share it with channels. The plan declares this and leaves it out of scope.

## Checked and sound
- Header and base commit `b192d9d` match `git log -1`. The plan is 501 lines. RED Tasks 1–3 come
  before GREEN, with the test-reviewer as the gate. *Found while building* is empty, and no task
  commits.
- Nothing is built on a 🔴 entry (D16, D18 and D28 were considered and stay untouched). D44 is the
  next free register id.
- `POST /api/v1/channels/dm` at red is a 405: only GET, PATCH and DELETE are on `/{channel_id}`, so
  Starlette matches the path but not the method. `/api/v1/channels` is in the Ingress allow-list at
  `ingress.yaml:62`.
- `ON CONFLICT … index_where` matches the partial index. The loser's next statement under READ
  COMMITTED (default engine, `db.py:21`) sees the winner's row.
- D15 first-send detection: emitting none is impossible under any commit order. A duplicate is
  allowed by the issue.
- D16 matches query-core 5.101.4 (`query.ts:411-419`): cancel only with data, otherwise the
  in-flight promise is reused.
- The listing rule is only in `list_page`, so `get_visible`, `join_channel` (`realtime.py:251`), send
  and typing still reach an empty DM. `visible_ids` needs no change for search.
- `VisibleChannel.dm_partner_id` defaults to `None`, so `test_read_markers.py:142` and
  `channels.create` are unaffected. `ChannelResponse` is built only in `_as_channel`.
- These fixtures and line references exist as cited: `hears_nothing` (`test_read_state.py:64-66`),
  `realtime_url_for(asset_internal_url=, service_token_url=)`, `asset_stub`, the early return the
  search test avoids (`test_search.py:117-118`), `test_channels.py:169-174`, `CreateChannelDialog.tsx:55-56`,
  `useChannelSocket.test.tsx:356`, the delete detail string, and `user_typing`.
- BDD: the reused phrases exist in `steps/conftest.py`. The new ones don't collide with
  `Ada sees "{body}" in the channel`, which is a full match. `ADA_NAME`/`GRACE_NAME` are the display
  names. The last `Then` is in Ada's window, so it proves the server. BDD truncation needs no change,
  since no new table is added.
- Expected reds: `ModuleNotFoundError` is right for the whole of `test_dms.py`, and the dataclass
  `TypeError` and `KeyError` for `test_dm_dto.py`. Vitest new modules fail as load failures, and
  modified files as assertions.
