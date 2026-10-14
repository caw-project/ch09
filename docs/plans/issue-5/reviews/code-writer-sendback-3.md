# Send-back from the code-writer — issue 5

The production code and the record are built and every new SPA test passes. Three Python
integration tests cannot pass against a correct build, and the plan's own ripple edits to
existing test files (Task 6) were never made — I may not write tests, and the unmade edits
break `tsc`, so the frontend image cannot build and **the e2e layer cannot run**. All four items are
the test-writer's.

## 1. Ripple edits to existing tests (Task 6's *Ripple* bullet) — blocks `tsc`, the build and e2e

The composer's prop is now `channelTitle` (plan interface), and nothing in these files was updated:

- `src/frontend/src/features/channels/MessageComposer.test.tsx:40` — `channelName="general"` →
  `channelTitle="#general"`.
- `src/frontend/src/features/channels/MessageComposer.attachments.test.tsx:37` — same;
  `:256` — `channelName={channelId}` → ``channelTitle={`#${channelId}`}``.
  Their `Message #…` queries stay as they are.
- `src/frontend/src/features/channels/CreateChannelDialog.test.tsx` (`:103-110`) — its `ChatLayout`
  render now loads the directory (`DirectMessageList`) and `setup.ts:32` fails an unstubbed
  request: add `auth.members([...])` (3 tests fail today: `creates "general"…`, `"team-42"`, `"Design-Review"`).
- Plan also lists `ChatLayout.test.tsx`, `ChatLayout.attachments.test.tsx` and `App.test.tsx:93` for
  the same stub; they pass today (they already stub the directory, or tolerate it) — check and add only if needed.

Printed: `npm --prefix src/frontend run typecheck` → 3 × TS2322 (`channelName` does not exist); Vitest
`21 failed | 466 passed` — 14 + 7 composer tests and 3 `CreateChannelDialog` tests, all from the above.
Nothing in the new tests fails.

## 2. `test_dms.py::test_both_members_can_use_every_message_route` — history is read before the send it expects

`history` (`GET …/messages`) is fetched at line 283, **before** Grace's `send` at 284. It cannot
contain `"from grace"`: `assert ['root'] == ['from grace', 'root']` fails at line 301. A correct build
gives `['root']`. Smallest fix: fetch `history` after Grace's send (or assert `["root"]`).

## 3. `test_dm_realtime.py::test_a_reply_does_not_announce_a_dm` — a reply legitimately emits `thread_summary_changed`

After Grace hears the reply's `message_received` (line 173), `hears_nothing` (174) fails with
`DID NOT RAISE TimeoutError`: the server publishes `thread_summary_changed` to the channel room for
every reply (`routers/messages.py:175`, `realtime.publish_thread_summary_changed`; issue 3, unchanged).
A build without `channel_added` on replies still emits it. Smallest fix: receive and assert the
`thread_summary_changed` event, *then* `hears_nothing` — so the test pins "no `channel_added`" and not
"no event of any kind".

## 4. `test_schema.py::test_the_dm_pair_index_is_unique_and_partial_on_kind_dm` — pins a rendering the plan's column can't give

`channels.kind` is `varchar` (migration 0001, `sa.String()`), so Postgres renders the predicate as
`WHERE (((kind)::text = 'dm'::text)` — printed: `CREATE UNIQUE INDEX ux_channels_dm_pair ON public.channels
USING btree (workspace_id, name) WHERE ((kind)::text = 'dm'::text)`. The test asserts the exact string
`WHERE (kind = 'dm'::text)`, which a `varchar` column never prints (the existing public-name test says
"match the parts, not the spelling"). Smallest fix: assert `"WHERE"` and `"'dm'"` in the definition, as
`test_the_public_name_index_is_partial_and_case_folded` does.

## 5. Docstrings only (plan decision 14, Task 7's sweep)

`tests/unit/test_channel_rules.py:96` and `tests/integration/test_channels.py:170` still say
"`dm` exists in the schema (D8b) … a DM has no name to give". Assertions stay; reword to "a DM is opened
through `POST /channels/dm`, not created by name".

## What I did not do

Rerun e2e: `docker/frontend/Dockerfile` runs `npm run build` (`tsc -b && vite build`), which fails on
item 1. When it returns, the journey `direct_messages.feature` gets its first run from me.
