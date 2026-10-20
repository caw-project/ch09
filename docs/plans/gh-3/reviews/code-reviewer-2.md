# Code review — gh-3, round 2: approved

Round 1's only blocking finding was a major one in the record: three places still said D28 is
open and that no preferences exist. All three are now reworded, and they match the code. The
two minor findings were left for the human with a reason that holds, because each needs a red
test first (D32). No code changed in this round, and the test evidence still covers the tree.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. The D28 sweep left three stale statements (major) | Fixed: doc 06's Styling row, the `index.css` comment and the root `README.md` | **resolved**. Each now says preferences exist in Auth (D28), a theme is not one of their keys, and the palette stays light-only. The `index.css` claim "only `clock` is" matches `KEYS = {"clock": …}` in `auth/preferences.py:36`. |
| 2. Back to chat after a switch made on a channel page (minor) | Left for a later stage: it needs a red test first | **let go**. This was my own recommendation in round 1. It stays under *Left for the human*. |
| 3. A failed background refetch on Settings drops an edit (minor) | Left for a later stage, for the same reason | **let go**. Kept under *Left for the human*. |

## What ran

- `git diff f145a55 f8e5314` showed `README.md`, `docs/design/06-frontend-spa.md`,
  `src/frontend/src/index.css` (comment text only), the green report, the test report and `run/`.
  No code, test, helper or fixture changed.
- Grep over the tree (outside `docs/plans/`) for `no user-preferences|D28 is open|D28 🔴|Revisit
  when preferences|nowhere to store`. It found only:
  - the three reworded lines;
  - `docs/adr/260815-tailwind-v4…`, an ADR that is history and correctly left as written;
  - `docs/issues/009.md`, a different issue that quotes the old text.
- `npm --prefix src/frontend run build` printed ✓ built. The edited CSS comment still closes,
  and the stylesheet compiles (16.01 kB). Nothing tracked was left behind.
- **Test report.** `docs/test-report.md` shows:
  - Lint ✅ at `f145a55-dirty`, rerun after this round's edits;
  - Unit ✅ 1973 and Integration ✅ 616 at `94bb827`;
  - E2E ✅ 25 at `08552a6-dirty`.

  `git diff --name-only 94bb827 HEAD` lists only Markdown, the plan dir, the report and the
  `index.css` comment. Per *A rework pass*, a comments-only change reruns lint and nothing else.
  The e2e evidence was checked in round 1 and is unaffected.
- I made no mutants or probes this round. No code changed, so none of round 1's can give a
  different result. There was no sketch to clean.

## Findings

None.

## Unpinned

These are carried over from round 1 unchanged:
- The rename's refetch of a directory that had no data yet. A probe showed the real code is
  right, but no approved test holds it.
- `hourCycle` over `hour12`. Only reading holds it.
- `is_display_name_conflict` re-raising other IntegrityErrors.
- The migration's `LOCK TABLE` and its `version`/`updated_at` bump.
- `completeSignIn` clearing the return path on each failure branch.

## Left for the human

- **Round 1 finding 2 (minor).** After a workspace switch made on a channel page, Back to chat
  goes to `{new workspace, old channel}` and shows a 404, not `/`. To fix it, record
  `lastChannel` only once the channel's detail query has loaded, or only when `channelId`
  changes. Round 1's probe in `App.test.tsx` is the red test to start from.
- **Round 1 finding 3 (minor).** On Settings, a failed background refetch replaces the form with
  the error banner and loses typed text. To fix it, show the banner only when
  `data === undefined`. It needs a red test first.
- The ProfileSection field error stays after the user edits the field, until the next save.
  This is cosmetic.
- The first real run on the Compose stack, as the green report lists: 0002 over seeded
  duplicates, a rename seen from a second browser, a name in capitals that someone else holds,
  24-hour time, and a return to `/settings` after signing in.
- 12/24-hour rendering in a non-en locale (e.g. `ja-JP`), in the browser.

## Checked and sound

- All three stale D28 statements are reworded and agree with the register (🟢) and with
  `KEYS`.
- The ADR and the other issue file that still hold the old wording are history, and correctly
  left as they are.
- Nothing outside the docs changed since round 1. The test report's layers still cover every
  input.
- Everything listed under round 1's *Checked and sound* still stands.
