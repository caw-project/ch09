# Plan review — issue 5, round 2: approved

All six round-1 findings are fixed, and I checked each fix against the code, not only against the
plan's word. The fixes break nothing beside them: the two-helper naming leaves every page-object
lookup and the composer's `Message #general` as they are, and the new header prop's callers are all
in the ripple. No critical or major finding is open.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. `data-channel-name` would gain a `#` | D18 now has two helpers. `channelLabel` is bare and feeds `data-channel-name`, `data-dm-name` and the header. `channelTitle` adds the `#` for the composer and search. | **resolved.** `chat_page.py:125`, `:208` (`channel-view`) and `:175`/`:102` (`channel-list-item`, still `channel.name` at `ChannelList.tsx:65`) match bare names. `MessageComposer.tsx:204-205` becomes `` `Message ${channelTitle}` ``, so `"Message #general"` comes out unchanged. |
| 2. Header and list interfaces were unspecified | *SPA interfaces* table: `ChannelHeader` takes a required `label`; `ChannelList` filters with `isDm` and reads no directory; `DirectMessageList` reads `useWorkspaceMembers` and sorts with `sortedDms`. | **resolved.** The header test's `renderHeader(channel, label)` and the DM case are concrete. The red ("`# dm:…`", Rename found) is what today's `ChannelHeader` would render. |
| 3. Ripple: `App.test.tsx`, `CreateChannelDialog.test.tsx` | Both added, plus `ChannelList.test.tsx:50` for the new `label`. | **resolved.** A grep for `<ChannelHeader` finds only `ChannelView.tsx:83`, `ChannelHeader.test.tsx:19` (`renderHeader`, modified) and `ChannelList.test.tsx:50`. A grep for `channelName` finds only `MessageComposer.test.tsx:40` and `.attachments.test.tsx:37`/`:256`, `ChannelView.tsx:113`, and `SearchPage.tsx:29/73`/`SearchResult.tsx`, all of which are in the map. `ChannelView.test.tsx:109` already stubs `auth.members` (`MessageList.tsx:118` reads the directory today). `SearchPage.tsx:34` already has `directory`, and `SearchPage.test.tsx:56` stubs it. |
| 4. Guard test green at red | Renamed `test_a_first_message_announces_a_dm_and_not_a_channel`: the DM's `channel_added` is asserted in the same test. `test_a_later_message_announces_nothing` asserts the first `channel_added`. | **resolved.** A build that never emits now fails both tests. |
| 5. 404 coverage gaps | The REST list adds `DELETE` message, `DELETE` reaction and `download-url`. The socket test is parametrized over `join_channel`, `send_message`, `edit_message`, `delete_message` and `mark_read`. | **resolved.** `routers/messages.py:429` runs `_visible_message` before Asset is asked. Socket `edit_message`/`delete_message` go through `messages._visible` (`messages.py:292`, `:360`) before the author check, so 404 and not 403. `mark_read` answers 404 "No such channel." (`realtime_writes.py:387-388`). |
| 6. Sibling-merge step | Added to Task 8. | **resolved.** |

## Findings

None.

## Left for later stages

- **Test pair:** `test/api.ts`'s `messaging.post` stub always answers 201, and the DM route answers
  200. That is harmless to `openapi-fetch`, but a test asserting the status needs its own handler.
- **Test pair:** the `ChannelHeader` DM case passes a `label` prop the component doesn't declare
  yet. Vitest doesn't typecheck, so the red is the assertion (`# dm:…`), not a type error. `tsc`
  is red until Task 6 anyway (`aChannel`'s `dmPartnerId`, per *How this plan runs*).
- **Human:** D14 (`POST /channels` still refuses `kind=dm`) and D17 (picker sorted by display name)
  are **assumed**. Both are defensible and cheap to change.
- **Human:** the sidebar reads one 50-row page of `GET /channels`. DMs (stored as `dm:…`) now
  share that page with channels. The plan declares this and leaves it out of scope.

## Checked and sound

- Base commit `b192d9d` matches `git log -1`. *Found while building* is empty, and no task commits.
  RED Tasks 1–3 come before GREEN, with the test-reviewer as the gate.
- Everything in round 1's *Checked and sound* still holds. The rework touched only D18, the Task 3
  SPA table and tests, the Task 2 lists, Task 6's ripple and Task 8.
