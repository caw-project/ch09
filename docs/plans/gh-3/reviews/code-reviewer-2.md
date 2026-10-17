# Code review — gh-3, round 2: approved

Both round-1 findings are fixed, and the fixes touch only docs and comments. The root README
and the `index.css` comment now agree with the register: D28 is 🟢, Auth stores preferences,
the clock is the only one, and the SPA is light-only because no theme preference exists. The
test report is stamped at the tree that was reviewed, and every layer passed.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. The sweep left D28 described as open (`README.md`, `index.css`) — major | Fixed. README: "D16 — still open … **D28** is settled: Auth stores user preferences (the first is the clock), but no theme preference exists, so the SPA stays light-only". `index.css`: "Auth now stores user preferences (D28), but a theme is not one of them … Revisit when a theme preference exists." | resolved. Both claims match the code: `user_preferences` holds only `clock`, and `index.css` has no dark palette |
| 2. A missing space in `update_me`'s docstring — minor | Fixed (`left alone; \`avatarAsset: null\``) | resolved |

## What ran

- `git diff HEAD~1 --stat`: `README.md`, `src/frontend/src/index.css`,
  `src/services/auth/auth/routers/users.py` (docstring only), `docs/test-report.md`, the green
  report and the runner's `run/` files. No code path changed, no test or helper was touched,
  and every file is one the findings named.
- Grep for `no user-preferences|D28 🔴|D28.*open|preferences exist` outside `docs/plans/` found
  two hits, and neither is stale for this slice:
  - `docs/adr/260815-tailwind-v4…`: an ADR records its own date, so leaving it was the round-1
    instruction.
  - `docs/issues/009.md`: another issue's text, quoting `CLAUDE.md`.
- `uv run ruff check src/services/auth`: all checks passed. `ruff format --check` on
  `users.py`: already formatted.
- Evidence for `scripts/test.sh`: `docs/test-report.md` is stamped `75fb0bc4a823-dirty`. That
  is the round-1 review commit, plus the writer's edits. The runner committed that tree as
  `fd6c38d` (`git log -1`), and nothing has changed since (`git status --short` is empty). The
  report shows Lint passed, Unit 1860, Integration 594 and End-to-end 25. All passed, which
  matches the green report's rerun note.
- No Vitest run, mutant or probe this round. The changes are a CSS comment, two README
  sentences and a Python docstring, so no test or mutant could reach them. The round-1 runs
  still hold for the unchanged code.

## Findings

None.

## Unpinned

Unchanged from round 1 (read there in full). The tests don't hold these, and the code is
right today:
- `ClockProvider` in the shell (probe 1).
- `onMutate`'s `cancelQueries` (probe 2).
- The profile cache write on a rename.
- `_is_name_conflict` matching on the constraint name.
- `_taken_keys` reading deleted rows.
- The avatar no-op writing nothing.

## Left for the human

- The assumed decisions: 12, 13, 15, 17/19/22, 25, 28, 29, 30, 34 and 37.
- Plan-review 2's optional item is still open. Two clock saves that fail in a row restore a
  value the server never stored. The next visit reads from the server.
- The first real run, as the green report lists it:
  - Rename Ada.
  - Take Grace's name in capitals (expect a 409 on the field).
  - Choose 24-hour and check an afternoon time in a channel, a thread summary and a search
    result.
  - Sign out on `/settings` and back in (expect to land on `/settings`).
- `docs/adr/260815-tailwind-v4-for-spa-styling.md` still says no preferences feature exists.
  That was true on its date, and is left alone on purpose.
- `origin/feature/gh-3-run1` edits the same files. Only one of the two branches can merge.

## Checked and sound

- README and `index.css` now match the register and the code.
- The docstring is fixed.
- Ruff is clean on Auth.
- The report stamp matches the reviewed tree, and all four layers passed.
- No file was touched outside the findings.
