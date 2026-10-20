# Test review — gh-3, round 2: approved

Both round-1 fixes are in place and nothing else changed in the files they touch. The 1 critical and 1 major finding are resolved; the minor ones are closed. This was a rework pass: I read the changed tests and did not rerun the sketches.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1 (critical) `clockSites` asserted synchronously on a TanStack update | `choose()` is now async. It runs `setQueryData` and a 20 ms real macrotask inside `await act(async …)`, and all three tests `await` it | **Resolved.** I read `clockSites.test.tsx`. The 20 ms timer outlasts TanStack's `setTimeout(0)` notify batch, so the re-render lands before the next `expect`. Both directions and the "not 15:07" halves are kept. In the round-1 sketch, `await vi.waitFor` turned the first of these tests green, and `choose` now waits for the same re-render. I did not rerun a sketch of the new `choose`. The tests fail at load until `./usePreferences` exists. |
| 2 (major) The focus test counted the first GET before it arrived | It now waits for `gets()` to have length 1 before the radio check. After leaving and returning it waits for `gets()` to have length 2 and for the 24-hour radio | **Resolved.** I read `PreferencesSection.test.tsx` lines 71–85. The wait is on the recorded request, so it no longer depends on whether the radios render before the fetch lands. `setPageAttention` exists in `test/page.ts`. |
| 3 (minor) The report said 10 tests for `PreferencesSection.test.tsx` | The report now says 9 | Resolved |
| 4 (minor) `chr()` constants in place of `\u` escapes | Accepted, no change | Let go |

## What ran

- No test or sketch was run this round. The Bash tool was denied in this environment, so the verdict rests on reading the two changed files and the helper they import.
- The round-1 results stand for every unchanged file. In round 1 I ran the Auth integration tests (33 failed, 12 passed), the unit files (2 load failures), the whole Vitest suite (21 failed, 503 passed) and the typecheck. I also ran the BDD bind check and the sketches.
- Round-1 correct-build sketch: 58 of 62 tests went green across `time`, `settings` and `session`. The 4 that stayed red are the two findings above.
- The round-1 wrong-build sketches (parallel saves, a stale response overwriting, a failure restoring the click's snapshot, a field seeded from the cache, no directory cancel, a sticky flag, no epoch) each failed their test.
- The round-1 sketches were not rerun. The round-2 changes touch only how the two tests wait; neither assertion changed.

## Findings

None new.

## Left for later stages

- The new `clockSites` helper and the focus test have not run against a build, because both files fail at load. The code-writer is their first run. If the 20 ms wait proves flaky under load, raise it. Every test asserts after it, so nothing else needs to change.
- Carried over from round 1: show an error state for a failed profile GET rather than seeding the field from a stale name.
- Carried over from round 1: check that `directoryRefresh.ts`'s `load` ignores the abort signal.
- Carried over from round 1: `App.test.tsx` has not been run against a build and uses 1 s `findBy` timeouts.
- Carried over from round 1: the radio during a focus refetch mid-save is deliberately not pinned.

## Checked and sound

- All other round-1 "checked and sound" items are untouched, so I did not recheck them. These are the Auth integration red reasons, the guards' positive halves, both sides of every boundary, the concurrency tests, the migration tests, the BDD binding and the untouched existing assertions.
