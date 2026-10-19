# Test review — gh-3, round 2: approved

The one major finding from round 1 is fixed: `SettingsPage.test.tsx` now has a test that ties the page to the rename hook. The minor findings are answered. I found nothing new. This round was checked by reading only, because Bash was denied in this session, so I ran no tests and no sketch. The round-1 sketches already showed that a correct build passes the page tests. The new test's helpers and fixtures check out in the installed source.

## Responses checked
| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. Nothing proves `SettingsPage` saves through the session- and directory-updating hook (major) | Fixed: *a saved rename reaches the session and the cached directory, and only the renamer* | **Resolved** (read, **unverified by running**) |
| Minor: `ChatLayout.test.tsx` leaves the directory GETs unstubbed | Fixed: stubs `auth.members([])` | Resolved |
| Minor: Decision 24 decomposed-form no-op, `{"theme": null}`, `skipToken` conflict with Decision 42, `Automatic` title | Left for later stages, with reasons | Accepted (see below) |

## What ran
- Nothing. Bash was refused ("don't ask" mode), so this is a reading review.
- I read `SettingsPage.test.tsx` lines 205–243, the report's *Review responses*, `test/api.ts` and `test/setup.ts`.

## Findings
None new.

Finding 1 is resolved by reading. The test does these things:
- It runs a real `session.restore()` against `auth.me`, `auth.workspaces` and `auth.refresh` stubs. The token carries a `wsp` claim that matches the seeded cache key.
- It seeds `['workspace-members', WS]` with Ada under the stale name `ada`, plus Grace.
- It saves "Ada L" through `auth.updateMe`, which echoes the body, and waits for "Saved". That is the last effect, so the assertions after it come after the save lands.
- It asserts the session profile's `displayName` is "Ada L", and the directory is exactly `{ada: 'Ada L', grace: 'Grace Hopper'}`.

A page-local mutation that writes only `['profile','me']` leaves the session at the old name and the directory row at `ada`, so it fails. A build that updates the session but not the directory fails the directory assertion. A build that rewrites every row fails the Grace assertion.

Helpers verified: `updateMe` (function reply), `preferencesBy`, `members`, `workspaces` and `refresh` all exist in `test/api.ts`. I did not confirm a session-state reset between tests (`setup.ts` has none), so a stale session from another test in the file is possible. The same pattern is already used in `useProfile.test.ts`, which went green against the round-1 sketch.

Two residual risks, which the code-writer should watch:
- **Red:** the new test is red only by the file's load failure (`Failed to resolve import "./SettingsPage"`). That is right, since every test in the file needs the page.
- **Green:** I could not sketch it. If it fails at green on `session.snapshot()`, check the session singleton's state before blaming the page.

## Left for later stages
- Plan Decision 42 (`queryFn: skipToken`) conflicts with the writer's `skipToken` test. The code-writer should record a departure: `useClock()` has no token, so a cache-only read through the query cache subscription is what the test needs. (The round-1 sketch passed it that way.)
- Minor: no Decision 24 decomposed-form no-op test, and no `{"theme": null}` unknown-key case.
- Minor: the `Automatic` test title claims more than it asserts. The stored half is covered by *shows only what this visit fetched*.
- Minor: the 12-hour halves of the three component tests pass at red, as declared.

## Checked and sound
- Everything verified in round 1 still stands, since the writer's changes touch only `SettingsPage.test.tsx` and `ChatLayout.test.tsx`. These are the 54 new failing tests, 23 wrong builds caught, and no existing assertion weakened.
- The new test uses no `data-testid`, queries by role and text, and ends on the session and cache state.
