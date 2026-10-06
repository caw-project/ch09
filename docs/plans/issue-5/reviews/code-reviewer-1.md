# Code review — issue 5, round 1: approved

The build does what the plan and the issue ask, on every path I walked. Every layer is green: the
journey passed in the committed report, and I reran the rest myself. Every mutant of a planned guard
was caught, or survived and was then probed against the real code, which passed. Three minor
findings, none blocking: a one-line drift in the hand-edited OpenAPI file, one inaccurate report
claim, and a picker that fails silently.

## Expectations

Written before opening the green report or any production file the writer touched.

**Task 4 — pair index, rules, listing.**
- *Unpinned:* `open_dm` calls `pair_name` before any write (self-DM writes nothing — pinned by count 0);
  members inserted only when `RETURNING` gave a row (a loser inserting members would hit the PK — a 500
  under the concurrent test, so likely pinned); the `ON CONFLICT` names `index_where` (without it
  Postgres can't infer a partial index — an error, pinned). Model `Index` mirrors the migration
  (alembic autogenerate drift, unpinned). Migration `down_revision = "0006"` and a `downgrade`.
- *Takes for granted:* READ COMMITTED (db.py session default) so the loser's `SELECT` after the
  blocked `ON CONFLICT` sees the winner. `_visible_query` already makes a DM member-only.
- *Could go wrong:* listing filter put in `_visible_query` (empty DM 404s by URL / join — pinned by
  `GET /channels/{dm}` 200); filter counting replies (a reply can't exist without a root, harmless);
  filter excluding tombstones (pinned). CH009: `select(Message…)` with no `deleted_at` filter needs a
  waiver *with a reason* in both `list_page` and `opens_dm`.
- *Wrong build:* `partner_of` parsing the name without checking `kind` (pinned by unit test).

**Task 5 — route, guards, `channel_added`.**
- *Unpinned:* R9 guard order 404 → DM-403 → admin-403 (pinned by the 404 parametrization and the
  detail); `require_user` only; 200 not 201; publishing *after* `message_received` and after commit
  on **both** paths; socket path's `opens_dm` check (test-reviewer: "later message announces nothing"
  is REST-only — a socket build that emits on every send would pass). `publish_channel_added` no-op
  when `sio is None`.
- *Takes for granted:* `opens_dm` runs in the send's transaction before the insert, and nothing earlier
  in that transaction has inserted the message (autoflush!). If `messages.create` were called first or
  an earlier `session.add` were flushed by the `exists` query, the check would always see a message and
  never emit. Each first-send path (REST text, REST attachment-only, socket) goes through one place.
- *Could go wrong:* `channel_added` published before commit; emitted to the channel room instead of the
  two personal rooms (pinned — Alan hears nothing); emitted on a reply (pinned); exception after commit
  in the publish skipping the job enqueue (ordering).
- *Record:* OpenAPI regenerated; `messaging.json` hand-edited would need to match the generator.

**Task 6 — SPA.**
- *Unpinned:* `ChannelList` must **not** read the directory; `UnreadBadge` shared; `useChannelNames`
  must produce titles on **both** paths — the list and the per-id detail fetch for a result outside the
  first page (test likely covers only the list path); `data-channel-name` = label (BDD only);
  `data-testid`s `dm-new`, `dm-pick` + `data-member-name`, `dm-list-item` + `data-dm-name`,
  `channel-unread-badge` inside the row (BDD only). Picker sorted and excluding caller (pinned).
  Picker closes after a pick / on Escape (unpinned UI).
- *Takes for granted:* `channel_added` handler's workspace is the socket effect's (deps include
  `workspaceId`); `reapplyAfterFetch` only fires on `success` — a failed first load then no reapply
  (the poll recovers in 30 s; acceptable). The list query is observed whenever the shell is up
  (`ChatLayout` mounts both lists).
- *Could go wrong:* the workspace check reading the workspace captured at mutate time instead of the
  current one (pinned by the switch test); navigating from the hook's `onSuccess` with a stale closure;
  invalidating `channelKeys.list(current)` instead of the started-in one (pinned one way only).
  `reapplyAfterFetch` when the list *has* data and is fetching — plain invalidate suffices; a build
  re-invalidating unconditionally causes an extra GET (harmless). Header: Rename/Archive/topic hidden
  for a DM whatever `myRole` (pinned); no `MemberPanel` and no `/members` fetch (pinned).
  Any other consumer of the channel list that assumes every row is a channel — `useChannelNames`'
  `known` map, any "first channel" redirect — must use titles/labels, not `name`.
- *Wrong builds to mutate:* drop the first-load reapply; `cancelRefetch:false`; skip `!isDm` filter;
  `channelTitle` returning `#` for a DM; workspace check removed; detail path of `useChannelNames`
  returning `name`.

**Task 7 — the record.** Register D8b 🟢 and new D44 🟡 naming `add_member` and `open_dm`; ADR file;
doc 02 route row, listing rule, R9 403, `dmPartnerId`, `channel_added`, index, §9 settled; doc 06 §5.2
section, picker, naming, `channel_added`, the first-load reapply, §5.4 label; vocabulary phrases;
comments at `models.py:60-62`, `CreateChannelDialog.tsx:56`; docstrings in two tests (done by the
test pair). Each claim must match the code, e.g. "R9 guard inside `_admin_or_403`" as built.

**Task 8.** `docs/test-report.md` at this tree's revision `-dirty`, e2e including `direct_messages`
passed, counts at or above baseline (unit 126, integration 276, Vitest 459, e2e 23).

## What ran

- `npm --prefix src/frontend test` → 50 files, **487 passed**. `run typecheck` → clean. `run lint` →
  clean. `run build` → built (`dist/` is ignored; the tree still has the same 55 entries).
- `uv run pytest src/services/messaging/tests/unit` → **134 passed**. `uv run ruff check
  src/services/messaging` → all checks passed.
- `uv run pytest` over integration `test_dms.py`, `test_dm_realtime.py`, `test_schema.py`,
  `test_search.py`, `test_channels.py` → **115 passed** (Docker reachable).
- `python3 .claude/hooks/checks/conventions.py` over the nine changed or new Messaging files → no
  findings.
- `scripts/test.sh` evidence: `docs/test-report.md` is at `b192d9d8eaa9-dirty` (= HEAD). Lint, Unit 894,
  Integration 531 and End-to-end 24 all passed, 0 failed, matching the green report's *What ran*.
  `build/test-results/e2e.xml` holds `test_grace_sees_the_direct_message_ada_starts_and_replies`
  (feature "Direct messages") with no failure element.
- **Mutants** (sketch; each reverted before the next):
  - F1 `useChannelSocket.ts`, first-load reapply disabled → `useChannelSocket.dm.test.tsx`: **caught** (1 failed).
  - F2a `useChannelNames.ts`, detail path returns `channel.name` → search tests: **caught**, but only by
    the channel `#design` test.
  - F2b the same path returns `` `#${channel.name}` `` (ignores a DM) → **survived** (23 passed).
  - F3 `DirectMessageList.tsx`, navigate without the workspace check → **caught** (switch test).
  - F4 `ChannelList.tsx`, DM filter disabled → **caught** (2 failed).
  - F5 `ChannelHeader.tsx`, controls for an admin on a DM → **caught**.
  - F6 `ChannelView.tsx`, `MemberPanel` on a DM → **caught**.
  - P1 `realtime_writes.py`, socket `first_in_dm` = "is a DM and top-level" (emits on every socket
    send) → `test_dm_realtime.py`: **survived** (13 passed).
  - P2 `channels.list_page`, listing filter always true → `test_dms.py`: **caught** (2 failed).
  - P3 `routers/channels.py`, `_manageable_or_403` dropped → **caught** (5 parametrized cases).
- **Probes** (real, unmutated code):
  - `search/probe.dm-detail.test.tsx`: a DM result **and** a channel result, both outside the
    list's first page, so both are resolved through `GET /channels/{id}`. DM row shows "Grace Hopper"
    with no `#` and no `dm:`; channel row shows `#design` → **passed**.
  - `integration/test_probe_dm_socket.py`: Grace has joined the DM room. Ada sends twice over the
    socket. First send → `message_received`, then `channel_added`. Second send →
    `message_received`, then nothing within 1 s → **passed**. Rerun against P1 → **failed**, so the
    probe catches that wrong build.
  - `unit/test_probe_openapi.py`: `messaging.openapi.document()` dumped as `python -m
    messaging.openapi` would, diffed against `src/frontend/openapi/messaging.json` → **failed**, one
    line (finding 1).
- `sketch.sh clean` run.

## Conformance

| Plan task or decision | Code | Outcome |
|---|---|---|
| D7/T4 pair key, `ux_channels_dm_pair` in model + migration 0007 (`down_revision "0006"`, downgrade) | `dms.pair_name`, `models.py`, `0007_dm_pair.py` | as planned |
| D8 `ON CONFLICT … index_where` then `SELECT`; members only by creator | `dms.open_dm` | as planned |
| D9 `POST /channels/dm` 200, `require_user`, commit then `_visible_or_404(with_read_state)` | `routers/channels.py` | as planned |
| D10 `dmPartnerId` required, no default | `schemas.py`, `_as_channel`, `_visible_from(row, user_id)` | as planned |
| D11 both `member`, no admin | `open_dm` | as planned |
| D12 403 wording, after 404, before admin check | `_manageable_or_403` inside `_admin_or_403` | departed (recorded): same order, one place; only the four management routes call it |
| D13 self-DM 400, `errors.userId`, nothing written | route + `pair_name` first | as planned |
| D14 `POST /channels` kind=dm still 400 | `validate_kind` unchanged | as planned |
| D15 first-send check before insert, publish after commit and after `message_received` | REST `send_message`, socket `send_message` | as planned |
| T4 listing rule in `list_page` only | `channels.list_page` | as planned |
| T5 `publish_channel_added` per reader room, no-op on `sio is None` | `realtime.py` | as planned |
| T5 regenerate contract | hand-edited, then `generate:api` | departed (recorded); one-line drift (finding 1) |
| D16 `channel_added` invalidates; reapply when no data and fetching | `useChannelSocket.ts` | as planned |
| D17 picker minus caller, `localeCompare` | `DirectMessageList` | as planned |
| D18 `channelLabel` / `channelTitle`; `data-channel-name` bare | `directMessages.ts`, `ChannelView`, `ChannelHeader`, composer, search | as planned |
| D19 workspace recorded; navigate only if current; invalidate started-in list | `useOpenDirectMessage(accessToken)` + ref in component | departed (recorded): signature takes no workspace; behaviour as planned |
| T6 `ChannelList` `!isDm`, no directory, empty state counts non-DMs | `ChannelList.tsx` | as planned |
| T6 badge shared | `UnreadBadge.tsx` | as planned (extracted, recorded) |
| T6 BDD markup `dm-new`, `dm-pick`+`data-member-name`, `dm-list-item`+`data-dm-name`, badge in row | `DirectMessageList.tsx` | as planned |
| D20/T7 register D8b 🟢, D44 🟡; ADR; doc 02, doc 06, vocabulary §34; comments | docs diff | as planned |
| T8 verification, *Found while building* | report, plan | as planned; by-hand three-browser run left for the human |

## Findings

### 1. `messaging.json` is not what the generator prints — minor
**Where:** `src/frontend/openapi/messaging.json:499` · **Checked:** the probe `test_probe_openapi.py`
`OpenDmRequest.description` holds raw em dashes (`Open — get or create —`). `python -m
messaging.openapi` (`json.dumps`, `ensure_ascii` on) prints `—`. That is the only differing line,
so the documents are the same JSON and `types/messaging.ts` is unaffected. But the green report
says to "regenerate once and expect no diff", and regenerating gives this one-line diff. Settled by
running the generator, which the human is already asked to do.

### 2. A *Beyond the tests* claim that isn't where it says — minor
**Where:** `03-green-report.md` *Beyond the tests*, "D44 doc-comments: … `add_member`'s docstring" ·
**Checked:** `grep D44 src` finds `schemas.py:110` and `routers/channels.py:214` only.
`channels.add_member` is unchanged: it already said the id is unchecked, but it doesn't name D44, and
neither does `dms.open_dm`'s docstring. The register's D44 row does name both functions, which is
what the plan's Task 7 asked for, so the record itself is right. Only the report overstates it.

### 3. A failed open shows nothing — minor
**Where:** `DirectMessageList.tsx:52-62` · **Checked:** read
`pick` closes the picker and calls `open.mutate`, and `open.error` is never rendered. A 503 or a
network failure leaves the user where they were, with no message. The plan doesn't ask for an error
state, and the picker can't send the one refusal it could provoke, a self-DM. Worth a
`ProblemBanner`, as `ChannelHeader` uses for its mutations.

## Unpinned

- **The socket path's "first message only" check** (P1 survived). The approved tests prove
  "a later message announces nothing" over REST only. A probe shows the real socket path
  announces only on the first send, and that the probe fails P1. Only reading protects it. The
  probe is a ready-made test if the test pair wants it.
- **A DM search result resolved through the channel detail** (F2b survived).
  `SearchPage.test.tsx` names a DM from the list only. A probe with both results outside the list
  passes against the real code: `useChannelNames` applies `channelTitle` on both paths.
- **`data-channel-name` is the bare label** and the `data-testid` markup are pinned by the BDD
  journey (passed) and no Vitest test, as the plan intended.
- **Carried from the test reviews:** the switch test doesn't pin that the *new* workspace's list is
  left alone, and the sender's own connection hearing `channel_added` is unpinned. Reading: the
  hook invalidates `variables.workspaceId` only, and the sender's sid is in its personal room,
  so it hears it.

## Left for the human

- Findings 1–3 (minor). For 1, regenerate `messaging.json` and expect exactly the one-line `—`
  diff. For 3, decide whether the picker should show a failed open.
- The issue's *Acceptance* run in three browsers (Ada, Grace, Alan) has not been done by anyone.
- **Assumed decisions to confirm:** D14 (`POST /channels` still refuses `kind=dm`) and D17 (picker
  sorted by display name).
- The sidebar's 50-row page now holds DMs (`dm:` names sort among channel names) as well as
  channels. This was declared out of scope in the plan.

## Checked and sound

- Commit, then publish: `channel_added` after `message_received` on both transports. It goes to the
  pair's personal rooms only, from `pair_of(visible.channel)`. `expire_on_commit=False`
  (`db.py:27`), so reading the channel after the commit is safe.
- `opens_dm` runs before `messages.create` on both paths, with nothing pending in the session, so
  autoflush can't make it see its own row. Under READ COMMITTED, the first message to commit always
  emits.
- `open_dm` writes nothing for a self-DM, and the loser of a race inserts no members. The listing
  filter is outside `_visible_query`, so an empty DM stays reachable by URL and by join.
- `_admin_or_403` is called only by rename, archive, add member and remove member. The 404 comes
  before the R9 403 (P3 caught).
- The `channel_added` handler closes over the effect's `workspaceId`, and the reapply fires only on
  success (F1 caught). The workspace check in the picker is pinned (F3).
- `ChannelList` reads no directory (F4), the header shows no controls or topic on a DM (F5), and the
  view shows no `MemberPanel` on a DM (F6).
- The docs describe what the code does. That includes doc 06's account of the first-load reapply and
  doc 02's account of the guard order.
- No file outside the file map apart from the recorded `UnreadBadge.tsx`. The test files changed
  only through the test pair's send-back round, which test-reviewer-3 approved.
