# Test review — gh-3, round 2: approved

Both round-1 blockers are answered. The `Zl` case now has the separator inside the name, with a trailing-separator case pinning "after trimming" from the other side. The preferences in-flight test now holds the PATCH, so it pins the `cancelQueries`. The writer's reasoned decline on `useProfile` stands.

## Responses checked
| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1 `Zl` unsatisfiable (critical) | Interior separator `"Ad" + LINE_SEP + "a"`. New `test_a_trailing_line_separator_is_trimmed_not_refused` expects `"Ada"`. | **Resolved.** I read `test_display_name_rules.py`. `str.strip()` removes a trailing U+2028 and does not touch an interior one, so a plan-conformant build (trim, then refuse Cc/Cf/Cs/Co/Cn/Zl/Zp) passes both cases. It matches my round-1 sketch, where the other three refusal cases passed. A build that refuses before trimming fails the trailing case. |
| 2 in-flight reads don't pin the cancel (major) | `usePreferences`: PATCH held, old GET released while it is pending, `24h` asserted before the PATCH is released. `useProfile`: declined, because plan decisions 29/30 have no cancel before a non-optimistic rename. | **Resolved.** The preferences change is in the test. With no `cancelQueries`, the old fetch lands 12h over the optimistic 24h while the PATCH is held, and the assertion at line 204 fails. With the cancel, the fetch is abandoned. The later invalidate read is the third read, which the test expects (`reads >= 3`). The `useProfile` decline is accepted. The plan (decision 30, task 3 row) says the invalidate's `cancelRefetch` replaces the old fetch, and no optimistic write exists to protect. Asserting the new name while the PATCH is pending would fail a correct build. |
| 3 minors | `Saved` now `findByText` then role check. The rest were left for a later stage. | Accepted as minor. |

## What ran
Rework pass, scoped to the changed files (`git show --stat HEAD`: `usePreferences.test.tsx`, `SettingsPage.test.tsx`, `test_display_name_rules.py` and the report). I read each diff target. I ran no tests and no new sketch. The change to the `Zl` case was walked by hand through `str.strip()`. The `usePreferences` test sits behind a missing module, so it could not run today. I did not re-sketch the no-cancel build this round: the test's mechanism is walked through above. That is **unverified by a run**, so a code-writer failure on this test should be read against that.

## Findings
None open.

## Left for later stages
- Unrecorded default `GET …/me/preferences` can't see a `useClock` that fetches (low risk: the plan makes it a cache subscription).
- `time.test.ts` "never prints 24:05" does not pin `hourCycle` on this Node. It guards other ICU builds.
- For the code-writer: the plan's Task 1 `Zl` row puts U+2028 at the end of the name, where `strip()` trims it. Follow decision 17 as written. The refusal applies to an interior separator, and a trailing one is trimmed and accepted.
- For the code-writer: `usePreferences.test.tsx` "not undone by a read already in flight" needs `cancelQueries` in `useSetClock`'s `onMutate`. If it fails for another reason, check the mutation's PATCH is held before the old GET is released.

## Checked and sound
Everything under round 1's *Checked and sound* is unchanged. No other test file changed apart from the one-line `SettingsPage` `Saved` query. No production code was written.
