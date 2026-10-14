# Red tests — issue 5, round 1

BDD outside-in as the plan recommends: one journey (`direct_messages.feature`), and everything
under it down the pyramid — 8 unit (Python), 49 integration cases (Python, parametrized; all fail),
Vitest (12 tests failing plus two files that fail to load, 16 tests in those two), 1 scenario.
**Every new test fails for the plan's reason except 2 guards that pass by design** (*Green by design*).
BDD can't run here; it parses and every step binds.

## Baseline
Run before the first edit of each file; no test failed at baseline.

| Existing file(s) changed | Before | After |
|---|---|---|
| `messaging/tests/integration/test_search.py` + `test_schema.py` | 28 passed (with real Elasticsearch) | 28 passed, + 2 new failing |
| `messaging/tests/unit` (whole directory, `test_dms.py` ignored for its load failure) | 126 passed | 126 passed, + 2 new failing |
| Vitest `ChannelHeader`, `ChannelList`, `ChannelView`, `SearchPage` tests | all passed | every pre-existing test still passes; only the new ones in the table fail (46 passed in the 7 files run, 12 failed + 2 files failed to load) |
| `tests/bdd` collection | 23 scenarios | 24 collected |

`test/factories.ts` (`aChannel` gains `dmPartnerId: null`) and `tests/bdd/pages/chat_page.py`
(DM methods added, nothing changed) have no tests of their own; their consumers are above.

## Tests
`405` = the first line of every Python route test: `assert 405 == 200` at `open_dm` (the path matches
`/{channel_id}`, which has no POST), as the plan says. Counts are per parametrized case.

| File · test | Layer | Task | Proves | Observed red (verbatim first line) | Match |
|---|---|---|---|---|---|
| `unit/test_dms.py` · all 6 | unit | 1 | pair key, self-refusal, partner, kind-not-name, `check_manageable` | `ImportError: cannot import name 'dms' from 'messaging'` (load failure; every test needs the module) | ✔ (ImportError, not ModuleNotFoundError — same cause) |
| `unit/test_dm_dto.py` · `test_the_dto_carries_the_partner` | unit | 1 | `dmPartnerId` dumped | `TypeError: VisibleChannel.__init__() got an unexpected keyword argument 'dm_partner_id'` | ✔ |
| `unit/test_dm_dto.py` · `test_a_channel_dto_has_a_null_partner_key` | unit | 1 | key present, `None`, on a public channel | `AssertionError: assert 'dmPartnerId' in {…}` | ≈ plan said `KeyError`; I assert presence first so the failure names the key |
| `integration/test_dms.py` · all 34 cases — opening twice, at once, other workspace, self (400), any role, empty unlisted, listed once a message, listing is per-DM, tombstone stays listed, partner on every response, 403 refusals ×5, author-only delete, every member route, 404 for a third user ×17 | integration | 2 | R2–R9, R11 | `assert 405 == 200` (all 47 route cases); `test_opening_at_once…` fails at its status list `[405, 405, …] == [200, …]` | ✔ |
| `integration/test_dm_realtime.py` · 13 cases — first REST / socket / attachment-only send, later message, reply, DM-not-channel, two at once, third user ×5, typing | integration | 2 | R10, R11, R8 | `AssertionError: {"type":…"status":405,"instance":"/api/v1/channels/dm"…}` (the helper's assert prints the body) | ✔ same cause |
| `integration/test_search.py` · `test_a_dm_is_searchable_by_its_members_only` | integration | 2 | R11 | `assert 405 == 200` (open) | ✔ |
| `integration/test_schema.py` · `test_the_dm_pair_index_is_unique_and_partial_on_kind_dm` | integration | 2 | `ux_channels_dm_pair` | `AssertionError: no index named ux_channels_dm_pair` / `assert 0 == 1` | ✔ |
| `directMessages.test.ts` · 8 | Vitest | 3 | `isDm`, `channelLabel`, `channelTitle`, `sortedDms` | `Failed to resolve import "./directMessages"` (load; all need it) | ✔ |
| `DirectMessageList.test.tsx` · 8 | Vitest | 3 | section, badge/bold, picker, navigation, workspace switch | `Failed to resolve import "./DirectMessageList"` (load; all need it) | ✔ |
| `useChannelSocket.dm.test.tsx` · `refetches the channel list…` | Vitest | 3 | `channel_added` → list refetch | `AssertionError: expected false to be true` | ✔ no listener |
| same · both `while a poll is in flight` tests | Vitest | 3 | event cancels the poll's fetch; DM survives either order | `expected [ … ] to have a length of 3 but got 2` | ✔ |
| same · `fetches again … first load` | Vitest | 3 | reapply after first load | `expected [ … ] to have a length of 2 but got 1` | ✔ |
| `ChannelHeader.test.tsx` · 3 DM cases | Vitest | 3 | label, no `#`, no topic, no controls | `AssertionError: expected '# dm:aaa:bbb' to be 'Grace Hopper'` | ✔ (plan also expected "Rename is found"; the heading assert comes first in the same test) |
| `ChannelList.test.tsx` · `lists the channels of a mixed response…` | Vitest | 3 | DM row hidden | `expected [ 'general', 'dm:aaa:bbb', 'random' ] to deeply equal [ 'general', 'random' ]` | ✔ |
| `ChannelList.test.tsx` · `invites the first channel when only direct messages come back` | Vitest | 3 | empty state counts non-DMs (**added**) | `Unable to find an element with the text: No channels yet…` | ✔ |
| `ChannelView.test.tsx` · `is composed to the other person…` | Vitest | 3 | placeholder, header, no member panel | `Unable to find role="textbox" and name "Message Grace Hopper"` | ✔ (plan said "Members is found"; the composer anchor fails first) |
| `ChannelView.test.tsx` · `opens a thread beside the messages` | Vitest | 3 | thread opens, still no Members | same textbox error | ✔ |
| `SearchPage.test.tsx` · `names a result in a direct message…` | Vitest | 3 | label, no `#`, channel result unchanged | `Unable to find an element with the text: Grace Hopper` | ✔ (shows `#dm:…` instead) |

### Green by design (guards that pass today — their positive half for a DM test that fails)
- `ChannelHeader` · `still puts the # on a channel…` — pins `# general` so "no `#`" for a DM isn't "no `#` anywhere".
- `ChannelView` · `still shows the member panel and a # for a public channel` — same contrast for the view.
- (`ChannelHeader` · `has no rename or archive…` shows the public admin's controls first, which passes, then fails on the
  DM half — the one test is counted as failing.)

### Wrong builds each guard fails
- `test_opening_at_once` — check-then-insert instead of `ON CONFLICT`; a pair key not sorted; a unique index on `name` alone.
- `test_the_listing_rule_is_per_dm` — "caller has any DM with a message" instead of this DM's own.
- `test_a_dm_cannot_be_changed` — leaving today's `_admin_or_403` (403 with the wrong detail), asserted `!= NOT_ADMIN`.
- `test_a_first_message_announces_a_dm_and_not_a_channel` — emitting on every channel's first message.
- `test_a_later_message_announces_nothing` / `test_a_reply_does_not_announce_a_dm` — emitting on every send; counting replies as first messages.
- `poll in flight` tests — `refetchQueries({cancelRefetch:false})` (joins the old fetch → 2 requests, not 3).
- `first load` test — plain `invalidateQueries` (joins the in-flight fetch → never a second GET).
- workspace switch — navigating or invalidating whatever workspace is current when the POST returns.

## Types
`npm run typecheck`: 16 errors, all expected, none from anything else:
- `dmPartnerId` unknown on `Channel`/`Partial<Channel>` (factories + 9 test call sites) — Task 5 regenerates `types/messaging.ts`.
- `label` not a prop of `ChannelHeader` (×2, `ChannelHeader.test`, `ChannelList.test`) — Task 6.
- `Cannot find module './directMessages'` and `'./DirectMessageList'` — Task 6.
- `'/api/v1/channels/dm'` not a `PathsWith<'post'>` (×2) — Task 5's contract.
- `directMessages.test.ts(82)` `Parameter 'c' implicitly has an 'any' type` — follows from the missing module.

## BDD
`uv run pytest tests/bdd --collect-only -q`: 24 collected (23 + 1). `--generate-missing --feature tests/bdd/features`
prints no stub — every step binds. Expected red, scenario "Grace sees the direct message Ada starts, and replies":
`When Ada starts a direct message with Grace` stops at `page.get_by_test_id("dm-new").click()` (no such element).
Past that, in order: `dm-pick` with `data-member-name='grace'`; `channel-view[data-channel-name='grace']` (the label bare, no `#`);
`dm-list-item[data-dm-name='ada']` appearing in Grace's sidebar by `channel_added` with `channel-unread-badge[data-count='1']`.

## Departures from the plan
- **Added** `test_the_listing_rule_is_per_dm` (integration), `test_a_reply_does_not_announce_a_dm` (integration),
  `ChannelList` "only DMs come back → empty state" (plan says the empty state counts non-DMs, no test named it),
  and `DirectMessageList` "navigates when the workspace is unchanged" (the plan's "same test without the switch").
- `ChannelView.test.tsx`: three cases rather than the plan's two — a public-channel contrast and the thread case split out.
- Socket test `test_a_first_socket_send_announces_the_dm` asserts Grace and Ada's second tab, **not the sending connection** —
  whether the sender's own `sid` hears it is the plan's silence, so it is left unpinned.
- The 404 parametrization also covers rename/archive/add/remove-member and mark-read (the plan's list plus the member writes),
  proving the 404 is answered before R9's 403.
- No `data-testid` read in any Vitest file; the SPA tests query by role, label and text. `data-channel-name`'s bare label is
  pinned by `directMessages.test.ts` and the BDD journey, as the plan says.
- `test_dms.py` red is `ImportError`, not `ModuleNotFoundError` (`from messaging import dms`). Same cause.

## Picked up from earlier reviews
- plan-reviewer-2, test pair: *`messaging.post` stub always answers 201, the DM route 200.* The `DirectMessageList` tests don't assert
  the status, only the body and navigation, so the stub is used as is. If a later test needs the 200, `api.ts` needs a handler.
- plan-reviewer-2, test pair: *`ChannelHeader`'s DM case passes a prop the component doesn't declare; red is the assertion.* Confirmed —
  `expected '# dm:aaa:bbb' to be 'Grace Hopper'`; `tsc` carries the type error (above).

## For the code-writer
- **Markup the tests need, by role and text** (Vitest): `DirectMessageList` is a `region` named "Direct messages"; a button named
  "New direct message"; each picker entry's text is the member's display name and clicking it picks them (any element, button or
  item); DM rows are `link`s whose text content is the partner's name (plus the badge's `aria-label`); bold is `font-semibold` on the
  name element, as `ChannelList`. `ChannelView` gives the composer `aria-label` and `placeholder` `Message <label>`; the header
  heading's `textContent` is exactly the label for a DM and `# name` for a channel.
- **Header test reads `getByRole('heading', {level: 2})`** — one `h2` in the header.
- `useChannelSocket.dm.test.tsx` mounts `useChannels` beside the socket, as `ChatLayout` does; the second GET must come from
  `channel_added`, not from `cancelRefetch: false`. No connect is emitted in those tests; the handler must work on `serverEmit` alone.
- Workspace-switch test: the mutation must settle with `isMutating() === 0` and invalidate `channelKeys.list(<starting workspace>)`
  with the component still mounted; `rerender` changes only `workspaceId`.
- Python: the 404 tests expect `detail == "No such channel."` on rename/archive/member writes for a non-member, i.e. 404 before the R9 guard.
- `channel_added` is asserted **after** `message_received` on the same room-joined connection (commit, then publish, in that order).
- Step `Ada sees "…" in the channel without reloading` is new in `test_dm_steps.py`; the plan lists it as such.
- Frontend types: `test/factories.ts` already carries `dmPartnerId: null`; regenerating the contract turns 14 of the 16 `tsc` errors green.

## Review responses
Round 2 (test-reviewer-1):
1. **Fixed (critical).** `ChannelView.test.tsx` › `a direct message`: (a) a block-level `beforeEach` sets
   `useChatStore…setConnectionStatus('connected')`, so the composer's placeholder is `Message <label>` rather than
   `Reconnecting…`; (b) the "no member panel" request check now matches `/channels/${dm.id}/members`, not any path ending
   `/members` (the workspace directory call also does). Reran the file: 12 passed (all pre-existing + public-channel contrast), the two
   DM cases still red at `Unable to find role="textbox" and name "Message Grace Hopper"` (no DM label in the view yet) — the plan's reason.
   Wrong build the fixed check fails: a `ChannelView` that still fetches `GET /channels/:id/members` for a DM.
Round 3 (code-writer send-back 3) — code exists, so these run green against it:
1. **Fixed.** `MessageComposer.test.tsx` and `MessageComposer.attachments.test.tsx` pass `channelTitle` (`"#general"`, `` `#${channelId}` ``). `CreateChannelDialog.test.tsx` stubs `auth.members([...])` for the `ChatLayout` render; its final count now filters links by `/c/` href, because the sidebar holds a second list (the DM section), so `getByRole('list')` was ambiguous. `ChatLayout*` and `App.test.tsx` pass unchanged, so no stub added. Typecheck clean; Vitest 50 files / 487 passed.
2. **Fixed.** `test_both_members_can_use_every_message_route` fetches history after Grace's send.
3. **Fixed.** `test_a_reply_does_not_announce_a_dm` receives `thread_summary_changed` (issue 3) before `hears_nothing`, so it pins "no `channel_added`". Wrong build it fails: emitting `channel_added` on a reply.
4. **Fixed.** `test_the_dm_pair_index…` asserts `WHERE` and `'dm'`, not the exact rendering. It still fails if the index is not partial on `dm`.
5. **Fixed.** Docstrings in `test_channel_rules.py` and `test_channels.py` reworded.
Reran against the built code: 125 Python tests passed across the five touched files.

Round 2 (continued):
- Left for later stages (minor), acknowledged: counts are 7 + 7 in `directMessages.test.ts` / `DirectMessageList.test.tsx` (14, not 16);
  socket "later message announces nothing" is REST-only; workspace-switch doesn't pin the new list untouched; sender's own connection unpinned.
