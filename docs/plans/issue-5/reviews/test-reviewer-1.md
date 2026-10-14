# Test review — issue 5, round 1: changes_requested

All 83 new Python and Vitest tests are red, 82 for the plan's reason, and the race, workspace-switch, header, list and search tests all
went green against a correct frontend sketch and red against the wrong builds I tried. One test, `ChannelView — a direct
message › is composed to the other person…`, can never pass against a correct build, for two separate reasons (critical).
The writer can fix it from this review.

## Expectations

Written from the issue, the plan and the code as it stands (no `messaging.dms`, no `/channels/dm` route, no
`channel_added`, no `dmPartnerId`, `ChannelHeader` has no `label`, `useChannelSocket` has no `channel_added`
listener), before opening the red report or any test.

**Unit (`test_dms.py`, `test_dm_dto.py`).**
- Fails today: `ModuleNotFoundError: messaging.dms` for the whole of `test_dms.py` (right: every test needs it);
  `TypeError … dm_partner_id` and `KeyError 'dmPartnerId'` for the DTO.
- Vacuous: a pair-name test that only checks symmetry (a constant passes); no test that `(a,b)` ≠ `(a,c)`; self-DM
  test with no positive half; `partner_of` tested one way round only (a build returning `low` always passes when the
  caller is `high`); a `private` channel with a `dm:` name not tested (kind-vs-name).
- Wrong build: key by `kind` only / by name prefix.

**Integration (`test_dms.py`).** Today every test fails at `open_dm` with 405 (or 404/422) — right reason.
- Vacuous: concurrency test with 1 each way (no race); "one DM" asserted on ids only, not on DB row count;
  listing rule asserted with no positive (an empty DM unlisted while an empty public channel *is*, and a DM with a
  message *is*); tombstone counted only if the delete really happened; a reply (thread message) counting as
  "has a message" — the issue says **top-level**, so a DM whose only message is a thread reply... (cannot exist
  without root, but a root deleted + reply) — look for pinning; unread 1 for Grace and 0 for Ada.
- `dmPartnerId`: both directions, null on public; a fixture where both users coincide proves nothing.
- R9: each of five routes refused with the DM-specific detail (not "Only a channel admin…"), and the public
  channel's admin path still works (positive half).
- R8 author-only delete: Grace 403, Ada 200.
- R11 third user: 404 with detail "No such channel." across the listed routes, with the DM existing and having messages.
- Wrong builds: check-then-insert (no unique index) — a 10-way gather should hit it; 201 vs 200 (the plan fixes 200);
  listing filter in `_visible_query` (empty DM would then 404 by URL — test must GET the empty DM 200).

**Realtime (`test_dm_realtime.py`).** Today `open_dm` fails 405.
- Vacuous: "hears nothing" without a positive anchor; Alan/other-workspace listening before Ada sends but not after;
  both Ada's tabs; emission to Ada's *own* room (R10 says both members, including the sender); first-send on all three
  paths (REST, socket, attachment-only); a later message announcing nothing (needs the first to have announced);
  public channel first message announcing nothing; a reply (thread) as first message not emitting — the plan says
  top-level only (check whether tested).
- Wrong build: emit on every message; emit only to the partner; emit to `channel:{id}` room; count-after-commit.

**Search / schema.** Search: Alan's `[]` with a public channel existing so early-return isn't the reason. Schema:
`ux_channels_dm_pair` unique, partial `kind = 'dm'`, on `(workspace_id, name)`; red = index missing.

**Vitest.** `directMessages.test.ts`: load failure (right). Vacuous: sort test where server order equals name order;
ids sorted same as names. `DirectMessageList.test.tsx`: load failure (right). Vacuous: the picker including the
caller; sorted by name when directory order already matches; workspace-switch test with no positive twin (navigation
without switch). `useChannelSocket.dm.test.tsx`: no `channel_added` listener at red → assertion failures. Races: old
fetch released before/after the new one; first load in flight; fake timers if any. Wrong build: invalidate only
(no reapply after first load); `refetchQueries` without cancel; handler matching on the wrong key (other workspace).
`ChannelHeader`: textContent exactly the name; DM with `myRole: 'admin'` shows no Rename (and channel still does);
no topic. `ChannelList`: DM row hidden, channels still shown. `ChannelView`: no Members for DM; Members for channel;
placeholder `Message <name>`. `SearchPage`: no `#`.

**BDD.** Steps bind; feature uses existing vocabulary; last `Then` is Ada seeing Grace's reply live (server state).
Selectors only in page objects; `@bdd` on Feature line only.

(Issue clauses to pin: "once it has at least one **top-level** message", "a tombstone still counts", "**both**
members' personal rooms", "every first-send path", "either order", "at the same instant", "Only a message's author
may delete".)

## What ran

- `uv run pytest src/services/messaging/tests/unit` → collection error `ImportError: cannot import name 'dms' from 'messaging'`
  (`test_dms.py`; the right load failure). `test_dm_dto.py` is red as reported (not re-run alone; reasoned from `VisibleChannel`/`_as_channel`).
- `uv run pytest` over `test_dms.py`, `test_dm_realtime.py`, `test_schema.py`, `test_search.py` (integration, Docker up) →
  **49 failed, 28 passed**. Every failure's first line is `assert 405 == 200` at `open_dm` (47 route/socket/search cases),
  `no index named ux_channels_dm_pair` (schema), as the report says. The 28 passes are the pre-existing tests in the two modified files.
- `npm --prefix src/frontend test --` the 7 Vitest files → 12 failed, 46 passed, 2 files failed to load (`./directMessages`,
  `./DirectMessageList`). Failure lines match the report's table.
- `npm run typecheck` → 16 `error TS`, as reported.
- `uv run pytest tests/bdd --collect-only -q` → 24 collected; `--generate-missing --feature tests/bdd/features` → no stub printed.
- **Sketches** (`sketch.sh frontend`, `sketch.sh test`; the SPA's plan interfaces, as small as passes):
  - *Correct*: `directMessages.ts`, `ChannelHeader` (`label`, no `#`/controls/topic for a DM), `ChannelView` (directory, label/title, no
    `MemberPanel`), composer prop, `ChannelList` filter, search titles, `DirectMessageList`, `channel_added` handler (invalidate + reapply
    when no data and fetching). → `directMessages`, `ChannelHeader`, `ChannelList`, `SearchPage`, `DirectMessageList`, all four
    `useChannelSocket.dm` tests and `ChannelView` thread/public cases **green**; `ChannelView › is composed to the other person…` **red** (finding 1).
  - *Same, with finding 1's two defects patched in the sketch's copy of the test* → placeholder defect gone, second defect shown (see finding 1).
  - *Wrong: `channel_added` with no reapply after first load* → `useChannelSocket.dm` first-load test **red**, other three green.
  - *Wrong: `refetchQueries({cancelRefetch:false})`* → both poll-in-flight tests and the first-load test **red**.
  - *Wrong: navigate after the mutation whatever the workspace* → the workspace-switch test **red**, its positive twin green.
- Backend sketch **not run**: the integration tests need a real route and SQL; I reasoned each against the plan's design instead
  (see *Checked and sound*). Unverified that they go green against a correct build — none of the findings below depends on it.

## Coverage

| Plan test or expectation | Test as written | Outcome |
|---|---|---|
| Task 1 unit — key symmetry, shared-person, self, partner both ways, kind-not-name, `check_manageable` | `test_dms.py` ×6, each with its positive half | present |
| Task 1 DTO | `test_dm_dto.py` ×2 | present (asserts presence first; fine) |
| Task 2 REST — twice/either order, 5+5 concurrent, other workspace, self (400 + nothing written), any role, empty unlisted *with* a public empty channel listed and URL 200, listed with unread 1/0, tombstone, partner both ways + null on public, 5 R9 refusals (detail ≠ NOT_ADMIN, nothing moved), author-only delete (403 + still there + 200), every member route, 404 ×17 with a real message, a reply, and a visible channel | `test_dms.py` | present; **added** `test_the_listing_rule_is_per_dm` (sound) |
| Task 2 realtime — REST/socket/attachment first send, later, reply, DM-vs-channel, two at once, socket 404 ×5, typing | `test_dm_realtime.py` | present; sender's own connection unpinned (reported, plan silent) |
| Search; schema index | `test_search.py`, `test_schema.py` | present |
| Task 3 BDD journey, steps, page object | feature + steps + `chat_page.py` | present; binds |
| Task 3 Vitest: helpers, section/badge/picker/navigation/switch, socket (3 orders), header, list, view, search | 7 files | present; **view test broken (finding 1)** |

## Findings

### 1. `ChannelView` DM test can never pass against a correct build — critical
**Where:** `ChannelView.test.tsx` › `ChannelView — a direct message` › `is composed to the other person by name, and has no member panel` ·
**Checked:** ran it against my correct sketch, twice.
Two independent defects, one test:
1. `expect(composer).toHaveAttribute('placeholder', 'Message Grace Hopper')` — `MessageComposer` shows `Reconnecting…` unless the store's
   `connectionStatus` is `'connected'` (`MessageComposer.tsx:104,205`). This `describe` never sets it (the only
   `setConnectionStatus('connected')` is at `:422`, in another block). Sketch: `expect(element).toHaveAttribute("placeholder", "Message Grace Hopper")` fails.
   (The `aria-label` half is fine and passed.) Fix: `useChatStore.getState().setConnectionStatus('connected')` in the block, as `:422` does.
2. `expect(requests().some((r) => r.url.pathname.endsWith('/members'))).toBe(false)` — the directory call is
   `GET /api/v1/workspaces/:id/members` (`test/api.ts:315`), which also ends in `/members`, and both `MessageList` today and `ChannelView` per the
   plan read it. With (1) patched, the sketch fails `expected true to be false`. Fix: match the *channel's* member route
   (`/channels/${dm.id}/members`), or drop the line — the `Members` heading assertion already proves no panel.
A code-writer building exactly to the plan could not turn this green. Everything else in the file passes.

## Left for later stages
- **Report counts:** `directMessages.test.ts` has 7 tests and `DirectMessageList.test.tsx` 7, not 8 and 8; "16 tests in those two files" is 14.
  Cosmetic.
- **Socket first-send, later message:** the "later message announces nothing" proof is REST only. A build that skips the `opens_dm` check
  on the *socket* `send_message` path only (emitting on every socket send) passes every socket test. Worth a case in `test_dm_realtime.py`
  if cheap; not blocking, since the shared helper is the plan's design.
- **Workspace switch test** pins that the started-in list is invalidated and the location unmoved, but not that the *new* workspace's list is left
  alone ("only"). A build also invalidating the current list passes; harmless.
- The sender's own connection hearing `channel_added` is unpinned (reported departure; accepted).

## Checked and sound
- Red for the right reason: 47 route/socket/search integration cases fail at `assert 405 == 200`; schema at the missing index; unit by `ImportError`
  (all six tests need the module); Vitest loads fail only where every test needs the module, other files fail on the new assertion.
- Existing tests: 28 pre-existing integration tests in `test_search.py`/`test_schema.py` pass; 46 Vitest pass; no existing assertion changed — only
  `renderHeader`'s signature and `ChannelList.test.tsx:50`'s `label`, both in the plan's ripple.
- Report matches the tree: every changed file is in the file map (`factories.ts`, `chat_page.py` included); no production code, config or docs touched.
- Guards have positive halves: empty DM unlisted *and* an empty public channel listed *and* URL 200; a later message / reply / channel's first message each
  assert the earlier `channel_added`/`message_received` first; Alan's search runs with a public channel present; Alan's 404s run with a real message and
  a visible channel; R9 asserts the DM-specific detail ≠ "Only a channel admin…" and that nothing moved.
- Clauses: top-level (reply test), tombstone, both members including the sender's second tab, every first-send path, 5-and-5 concurrent opens with row
  count 1 and member count 2, author-only delete both halves.
- Races proven by sketch in both orders and for the first load (finding-free).
- BDD: steps bind, `@bdd` on the Feature line, selectors only in the page object, last `Then` is Ada seeing Grace's reply live.

