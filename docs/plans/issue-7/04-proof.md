# Issue #7 — acceptance proof: accepted

## Summary
- When a member joins after Ada's tab loaded the directory, Ada's tab fetches the directory again on meeting the unknown id and shows the name, with no reload.
- Seen running on a fresh preview: Grace signed in for the first time and posted; Ada's never-navigated page showed "grace" as the author.
- Alan, also a first-time sign-in, started a DM; Ada's open page listed "alan" by name in *Direct messages*.
- After Ada's network dropped and returned (a message arriving during the outage) every author on her page showed a name, none a short id.
- SPA only: no service, route or chart change.

## Try it
- Origin: https://reservations-diy-reasons-energy.trycloudflare.com — sign in as ada@collabhub.dev / collabhub (grace@collabhub.dev, alan@collabhub.dev too)
- Quick-tunnel URLs die with cloudflared: `BRANCH=feature/issue-7 scripts/deploy.sh preview url`, or `preview up` for new ones
- Take it down: `BRANCH=feature/issue-7 scripts/deploy.sh preview down`

## Acceptance criteria
Requirements R1–R6 are internal (request counts, cache bookkeeping); the issue's three *Acceptance* checks are the visible ones.

| # | Criterion | Proven by | Result | Screenshot |
|---|---|---|---|---|
| A1 | Grace signs in for the first time and posts; Ada sees "grace" without reloading | `test_a_newcomers_message_shows_her_name_without_a_reload` — Ada's page loaded the directory first; Grace's first-ever sign-in follows; Ada's page is never navigated; also counts 1–3 `/members` requests on it | **proven** (old code keeps the short id up to 5 min, so the name assertion would fail) | [shot](../../../build/acceptance/feature/screenshots/test-a-newcomers-message-shows-her-name-without-a-reload-chromium-ada-sees-grace-by-name.png) |
| A2 | Ada's DM list lists the newcomer by name | `test_a_newcomer_is_listed_by_name_in_the_dm_list` — Ada's page open; Alan's first-ever sign-in, DM to Ada; row looked up by `data-dm-name="alan"` | **proven** (Alan was unknown to Ada's directory; the row name comes from it) | [shot](../../../build/acceptance/feature/screenshots/test-a-newcomer-is-listed-by-name-in-the-dm-list-chromium-dm-list-names-alan.png) |
| A3 | Network drops and returns: nothing shows a short id that showed a name | `test_a_reconnect_never_turns_a_name_back_into_a_short_id` | **regression check** — Grace is already known there, so old code passes too. Discriminating: `useChannelSocket.test.tsx` "refetches the workspace directory on every connect" and the two R1+R5 tests | [shot](../../../build/acceptance/feature/screenshots/test-a-reconnect-never-turns-a-name-back-into-a-short-id-chromium-names-after-reconnect.png) |
| R1 unknown id refetches | `useWorkspaceMembers.test.tsx` "shows the short id while the refetch is in flight, then the name it brings" | Vitest | — | — |
| R2 one request at a time | same file: "asks once for several unknown ids…", "an unknown id seen while a refetch for another reason is in flight joins it" | Vitest | — | — |
| R3 departed ids quiet | same file: "a departed id starts no further refetch…", "a fetch for another reason clears the departed set…", "a departed member who rejoins…" | Vitest | — | — |
| R4 short id until the name arrives | first hook test; `MessageList.test.tsx` "shows a newcomer's name…" | Vitest | — | — |
| R5 reconnect refetches | `useChannelSocket.test.tsx` as in A3 | Vitest | — | — |
| R6 per workspace | hook tests "a refetch for one workspace lands in that workspace's cache…", "each workspace keeps its own departed set" | Vitest | — | — |

Totals: 2 of 3 visible criteria proven, 1 regression check (A3, discriminating test named); 6 internal rules each with named tests.

## Preview
- Branch `feature/issue-7`; commit `dca6fbb` plus uncommitted changes (deploy `dca6fbbd5003-preview-feature-issue-7-dirty`).
- Namespace `preview-feature-issue-7`; collabhub-deps and collabhub both installed at revision 1 (see `build/acceptance/preview-up.log`).
- Origin https://reservations-diy-reasons-energy.trycloudflare.com reachable; object-storage origin up.

## Standard smoke pack
Step 3: 6 passed, 0 failed, 0 skipped. The same six passed again beside the feature pack (9 passed, 25 s).

## Feature smoke pack
`build/acceptance/smoke/test_issue_7.py` — 3 passed.
- **newcomer's message** — Ada creates a channel and has it open (directory loaded; Grace not yet a member). Grace signs in for the first time in a new context, opens the channel and sends. Ada's untouched page shows author "grace", not an 8-hex id; 1–3 `/members` requests were seen on it after the sign-in.
- **DM list** — Alan signs in for the first time and starts a DM to Ada. Ada's sidebar lists "alan" under *Direct messages* with unread 1.
- **reconnect** — Ada goes offline until the SPA reports disconnected; Grace sends; Ada comes back online and rejoins the room; both messages show "grace", no `message-author` matches an 8-hex id.

Needs first-time state: A1 uses Grace and A2 uses Alan as first-time joiners, so each is a real newcomer **once per preview**. A rerun against this same preview passes but no longer exercises a stale directory.

## Screenshots
[build/acceptance/](../../../build/acceptance/) — `feature/screenshots/` (all 9 tests) and `standard/screenshots/`. I opened the three cited: each shows the named author or DM row, nothing cut off. Disposable: the PR uploads them.

## For the human
- **The short id is never observed.** The tests show the name arrived without a reload, not that a short id was on screen first ("briefly the short id" in the issue). The `/members` count (1–3) is the only live evidence of the request rules; exact per-id counts and the departed-id quiet path are proven only in Vitest.
- **Not done by hand:** the plan's Task 6 manual run's messaging-container restart and per-id request count (green report *Left for the human*; code-reviewer finding 1). This pack covers its two-browser and network-drop steps.
- **Assumed decisions (plan):** 7 (an id cleared by an other-reason fetch earns one more refetch), 14 (no tracker fetch before the first successful load), 15 (a failed refetch leaves its ids quiet), 16 (every connect, including the first, refetches), 17 (a TanStack retry counts as another reason), 18 (`nameFor` outside render untracked), 21 (a stale mount/focus fetch joining the tracker's own doesn't clear the departed set).
- **Departures:** red report — rejoin test uses an `anchorAnswer`; `scriptDirectory` helper added; R6 test loads both workspaces first. Green report — `if (workspaceId)` guard around `otherReason`.
- **Correction to the issue (plan):** installed TanStack 5.101.4's `refetchQueries`/`invalidateQueries` cancel and restart an in-flight fetch by default; the build passes `cancelRefetch: false`.
- **Open minors, code-reviewer-1:** doc 06 *Names* says "a mount" where only a stale mount or focus counts (`06-frontend-spa.md:313`); the *Naming* bullet at `:204` is ~140 chars where the section wraps near 95; tracker state lives as long as the `QueryClient` and nothing clears it on sign-out; four surviving mutants judged harmless (e.g. a failed-then-successful first load isn't driven by a test).
- **Seen in the screenshots, not this issue's:** Ada's page still shows "grace is typing…" after Grace's message has arrived and she has sent nothing further (A1 and A3 shots). Not checked whether it predates this branch; the typing indicator is untouched by the diff apart from the name it shows.

## The run
```
01 plan-writer done · opus
02 plan-reviewer changes_requested (2 major, 3 minor)
03 plan-writer done · opus
04 plan-reviewer approved
05 test-writer done · sonnet — 15 Vitest tests red
06 test-reviewer changes_requested (1 major)
07 test-writer done
08 test-reviewer approved
09 code-writer done · sonnet — 15 green, Vitest 503, e2e 24
10 code-reviewer approved (3 minor)
11 acceptance-reviewer approved (earlier preview; rerun on this one)
```
