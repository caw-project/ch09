# Exemplar implementation plan

This is the model the **plan-writer** agent follows (`.claude/agents/plan-writer.md`), and the
standard the **plan-reviewer** holds a plan to. It is a complete plan for an invented issue — *pin a
message to a channel* — annotated with why each part is there.

**The feature is not real. Do not build it, and do not copy its content:** copy its shape, and the
reasons. Every `> **Why:**` note records something a past plan got right, or something its build
found missing, with the evidence. A plan you write carries no `Why` notes.

When a build teaches something new, add it here, in the section it belongs to, with its citation.

## Before you write: the sweep

Most of what past builds found missing, a grep would have found first. Before drafting, run these
and put what they find into the file map:

| Look for | Because |
|---|---|
| Every caller of a function whose signature changes — **tests included** | Reactions made `_as_message(…, reactions=)` required; the file map missed `tests/unit/test_indexing.py` (`674db91`) |
| Every importer of anything moved or renamed | Plan A's helper move hit two BDD files and a README it never named (`5c15626`) |
| A new public route → `charts/collabhub/templates/ingress.yaml`'s allow-list | Search's route was missing from it until a deploy failed (`ff29137`) |
| A new env var → `.env.example`, `settings.py`, the chart's ConfigMap or Secret, `docker-compose*.yml` | CLAUDE.md: `.env.example` is the full contract |
| A decision this work settles → its ID, "still open", and the old behaviour, across `src/` and `docs/` | Helm scaling left `worker/settings.py` saying "D17, still open" (`e65e413`) |
| An API change → the OpenAPI regeneration, and the SPA's generated types and MSW stubs | The SPA is typed from it (D23); a stub that doesn't match fails `tsc` |
| A new table → the next Alembic number, and whether `tests/bdd/conftest.py`'s truncation reaches it | Read markers named that file *and* why it needed no change |
| Sibling branches in flight (`git worktree list`, `git branch --no-merged main`) | PR #2 and the scripts branch merged cleanly and still broke each other (`ff29137`) |
| Docstrings and design-doc sections that describe the old behaviour | Reactions Task 15 named them by file:line — and one it named never needed changing; check each |

## How long

**250–600 lines.** The 150–350-line plans (`10-test-report`, `02-build-deploy-test-scripts`, `05-*`)
matched their builds best. The 1,100–2,600-line plans wrote the diff out twice, and still missed what
only running revealed. The test-writer writes the tests and the code-writer writes the code; the plan
gives them what they cannot work out for themselves:

- **exact interfaces** — names, signatures, types, wire shapes — because each writer sees only the plan;
- **every test by name, layer and expected failure** — not its body;
- **code only where the reason *is* the value**: a migration's constraint, a non-obvious config
  line (the KEDA `lagCount` comment in `02-helm…:387-391`), a Gherkin scenario.

---

# Pinned messages — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** Anyone in a channel can pin a message, and everyone in the channel sees the pinned list
update live.

**Architecture:** A `channel_pins` table keyed `(channel_id, message_id)`, so pinning twice is `ON
CONFLICT DO NOTHING`. Two REST routes toggle a pin and return the channel's pins. A `pins_changed`
broadcast carries the whole list, so applying it is an idempotent replace. The SPA shows the list in
the channel header.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, python-socketio, pytest +
testcontainers · React 19, TanStack Query, Vitest + MSW · pytest-bdd + Playwright.

**Issue:** `docs/plans/issue-0/00-issue.md` — read it first. This plan argues from it and does not
repeat it.

**Worktree:** `../caw-issue-0`, branch `feature/issue-0`, from `main` at `2063966` — as the context
block's **Worktree:** line gives them; never built from the key.

> **Why:** every ch07 plan opens this way (`02-message-reactions…:1-31`). The base commit makes
> the baseline counts below checkable. The override note stops a skill's "commit" step being
> followed literally.

## Decisions

Decided by the issue:

| # | Question | Answer |
|---|---|---|
| 1 | Who may pin | Anyone who can see the channel |
| 2 | How many pins | At most 5 per channel; the sixth is refused |
| 3 | Deleted messages | A tombstone cannot be pinned, and deleting a message unpins it |

Taken in this plan — each needs the plan-reviewer's yes or no:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 4 | Where a pin is stored | New table `channel_pins`, not a `pinned_at` column on `messages` | The limit is per channel, so counting stays one indexed query. A column would add a write to the hottest table |
| 5 | The sixth pin | `409` with the reason `"This channel already has 5 pinned messages."` | 422 would mean the body was malformed, and it wasn't |
| 6 | What the broadcast carries | The whole list, not a delta | The same reasoning as reactions' authoritative count (D39): idempotent, and safe to apply from the response *and* the echo |
| 7 | The register | New entry D43, 🟢 once built | No existing entry covers pins |
| 8 | Pinning a message that is already pinned — **assumed** | `204`, the list unchanged, no broadcast | The issue doesn't say. Reactions treat a repeat as a no-op (doc 02 §3.1.6), and a `409` would make a double click an error. Changing it later is one branch in the route and one test |

Nothing here touches a 🔴 entry. **D16** (tombstone retention) is close, but not touched: a pin is
removed when its message is deleted, not when the tombstone is purged.

> **Why:** splitting *agreed* from *taken here* is what made the ch07 plans reviewable before any
> code existed (`10-test-report…:10-29`, `02-read-markers…:46-86`). Each call carries its
> alternative, so the reviewer can reject one without re-deriving it. Naming the nearest 🔴 and
> why it isn't touched is what a reviewer checks first. A row marked **assumed** fills a gap in
> the issue that nothing written settles: the run carries on with the best-fitting reading
> instead of stopping, and the human sees every such row at the end — so it says what changing
> it would cost.

## Corrections to the issue

**The issue says "unpin by deleting the pin's ID". Pins have no ID of their own** — the key is
`(channel_id, message_id)` — so unpin is `DELETE /channels/{id}/pins/{messageId}`. Task 7 writes
this back into doc 02.

> **Why:** a correction made while planning goes back into the spec in the same slice
> (`02-message-reactions…:34-47`, which the design doc now records at `01-…design.md:206-207`).
> If the issue is wrong in a way the code and docs don't correct, pick the reading that fits best
> and record it as an **assumed** decision row; it is `needs_human` only for what the shared
> context's *Stopping for a human* lists.

## Test approach — recommendation to the test pair

**BDD outside-in, with one journey.** This is a new capability a user sees, and only a real browser
proves that a pin made in one session appears in another. Write the journey first. Everything
under it goes down the pyramid.

| Behaviour | Layer | File |
|---|---|---|
| Ada pins a message; Grace sees it in the pinned list without a reload | **BDD** | `tests/bdd/features/pins.feature` |
| The 5-pin limit, the tombstone rule, and the order of the list | unit | `messaging/tests/unit/test_pins.py` |
| Pin and unpin over REST: idempotent, 404 for a channel you can't see, 409 on the sixth and on a tombstone; delete unpins | integration | `messaging/tests/integration/test_pins.py` |
| `pins_changed` reaches the channel's room only | integration | `messaging/tests/integration/test_realtime.py` |
| The header lists pins; the menu toggles; a `pins_changed` event replaces the cache | Vitest | `features/channels/PinnedList.test.tsx`, `usePins.test.ts` |

**What no test here covers:** the index that keeps counting pins fast. That is proven by reading
the migration, not by a timing test.

**Baseline**, from `docs/test-report.md` at `e4d3396`: Messaging unit 94 passed, integration 211
passed; Vitest 145 passed; end-to-end 19 passed.
Expected counts below are "N or more", because a sibling branch may land first.

> **Why:** the plan-writer recommends and the test pair decides, within reason.
> - **BDD** is for a big, new, user-facing capability, with one to three scenarios. It is also
>   right for a change to a journey the suite already has: sign-in, live delivery, routing to a
>   404, the session lifecycle.
> - **TDD** is the default for everything else: rules, APIs, workers, scripts, charts.
>
> Evidence:
> - Reactions justified exactly one journey: "a field rule belongs lower down"
>   (`01-message-reactions-design.md:281-284`).
> - Half of the old BDD suite was field rules, and D32 cut it from 41 tests to 15
>   (`ch07/01-test-pyramid-design.md:41-43`, `42d47ac`).
> - Naming what no test covers came from `02-read-markers…:88-106`. There, nothing closed the gaps
>   until the backfill found real bugs (`f72b551`), so close yours in this slice.
> - Baseline counts made red reviewable (`02-read-markers…:486-487`). Take them from
>   `docs/test-report.md`, which names the revision they were measured at. Counts moved when
>   siblings merged (`03-test-pyramid-handoff-integration.md:269`), hence "N or more".
>
> Had this been TDD, the table would have no BDD row, and the phase table below would have one RED
> phase fewer.

## Global constraints

- The workspace comes from the token's `wsp` claim only (CH001). A channel the caller can't see is a
  **404 `"No such channel."`**, never a 403 (CH004).
- `require_user`: pins are not in the fail-closed set of Conventions §5.2.
- **Commit, then publish.** Publishers do nothing when `sio is None`.
- No foreign key to Auth's rows. `message_id` and `channel_id` get real foreign keys, because both
  ends belong to Messaging.
- No new environment variable. No chart change: `/api/v1/channels` is already allowed by
  `charts/collabhub/templates/ingress.yaml:57` (checked).
- Everything else is as CLAUDE.md says. The hooks block on lint, and the conventions checker runs
  over what changed.

> **Why:** restate only the rules this work can break, and point at CLAUDE.md for the rest. A rule
> copied into a plan goes stale when the rule changes: two ch07 plans carried a "no tests" rule
> after D32 replaced it (`02-helm…:15`). "Checked" on the Ingress line is the sweep's result,
> written down.

## File map

| File | Change | Responsibility | Task |
|---|---|---|---|
| `messaging/tests/unit/test_pins.py` | create | the rules | 1 |
| `messaging/tests/integration/test_pins.py` | create | routes, SQL, delete-unpins | 2 |
| `messaging/tests/integration/test_realtime.py` | modify | `pins_changed` room | 2 |
| `tests/bdd/features/pins.feature` · `steps/test_pin_steps.py` · `pages/chat_page.py` | create · create · modify | the journey | 3 |
| `messaging/messaging/pins.py` | create | `MAX_PINS`, `may_pin`, `ordered`, add/remove/list | 4 |
| `messaging/messaging/models.py` | modify | `Pin` | 4 |
| `messaging/messaging/alembic/versions/0005_pins.py` | create | `channel_pins` | 4 |
| `messaging/messaging/routers/pins.py` · `main.py` | create · modify | two routes, registered | 5 |
| `messaging/messaging/routers/messages.py` | modify | delete removes the pin, in the same transaction | 5 |
| `messaging/messaging/realtime.py` | modify | `publish_pins_changed` | 5 |
| `src/frontend/openapi/messaging.json` · generated types | regenerate | the contract | 5 |
| `features/channels/PinnedList.test.tsx` · `usePins.test.ts` | create | the SPA's red | 3 |
| `lib/realtime/useChannelSocket.test.ts` | modify | its fake socket expects `pins_changed` — an existing test the change breaks | 3 |
| `features/channels/PinnedList.tsx` · `usePins.ts` · `ChannelHeader.tsx` · `MessageItem.tsx` | create · create · modify · modify | list, cache, menu item | 6 |
| `lib/realtime/useChannelSocket.ts` | modify | route `pins_changed` into the cache | 6 |
| `docs/design/02-messaging-service.md` · `07-open-decisions-register.md` · `docs/adr/…-pinned-messages.md` | modify · modify · create | the record | 7 |

Deliberately unchanged: `tests/bdd/conftest.py`, because its `TRUNCATE … CASCADE` on `messages`
reaches `channel_pins`.

Paths are relative to `src/services/` and `src/frontend/src/` where shortened.

> **Why:**
> - Read markers' diff matched its file map exactly, 21 files of 21, and it named the file it left
>   alone and why (`02-read-markers…:146-147`).
> - Reactions knew `useChannelSocket`'s tests would change, but said so only in its self-review,
>   and the build paid for it anyway (`02-message-reactions…:2584-2586`). Put the ripple in the
>   map.
> - Plan 07 had no file map and spread to 70 files (`92670b4`).

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–3 | test-writer | failing unit, integration, BDD and Vitest tests, each failing for the reason given — **test-reviewer gate** |
| GREEN — backend | 4–5 | code-writer | Tasks 1–2 pass; the contract regenerated |
| GREEN — SPA | 6 | code-writer | Task 3's Vitest tests and the journey pass |
| Finish | 7–8 | code-writer | the record, then verification |

The SPA's red can be written before the backend exists, because Task 3 types its stubs from the
contract shape in Task 2's interfaces. Until Task 5 regenerates the contract, `tsc` is red for the
same reason as the tests.

> **Why:** the phase table is what lets a reviewer see the gate (`02-message-reactions…:102-118`).
> Reactions needed two RED stops, because `aMessage()` is typed from the generated schema. Say
> why when a plan has two red phases, as it does here.

---

## Task 1: The rules (RED)

**Files:** `src/services/messaging/tests/unit/test_pins.py` (create)

**Interfaces** — produces the contract Task 4 implements, in `messaging.pins`:
- `MAX_PINS: int = 5`
- `class PinLimitError(Exception)`, `class TombstoneError(Exception)`
- `may_pin(message: Message, current: int) -> None`, which raises one of those two
- `ordered(pins: Iterable[Pin]) -> list[Pin]`: newest pin first, ties broken by `message_id`

| Test | Proves | Expected red |
|---|---|---|
| `test_a_sixth_pin_is_refused` | the limit | `ImportError: messaging.pins` |
| `test_a_tombstone_cannot_be_pinned` | the tombstone rule | same |
| `test_the_fifth_pin_is_allowed` | the limit is inclusive | same |
| `test_pins_list_newest_first` | the order | same |

Each test gets the house docstring, one line saying what breaks if the rule goes
(`tests/unit/test_message_policy.py`). Build `Message` rows with the unit conftest's factory
fixture. Never a session.

> **Why:** a test named for its behaviour, with its expected failure given, is reviewable before
> its body exists: the test-reviewer checks each one fails *for that reason*. "FAIL" alone let
> vacuous tests through (`00-scenario-vocabulary.md:449`).

## Task 2: The routes, the SQL and the broadcast (RED)

**Files:** `messaging/tests/integration/test_pins.py` (create), `test_realtime.py` (modify)

**Interfaces** — the wire contract that Tasks 3, 5 and 6 depend on:

```
PUT    /api/v1/channels/{channelId}/pins/{messageId}  → 200 PinsResponse
DELETE /api/v1/channels/{channelId}/pins/{messageId}  → 200 PinsResponse   (not pinned: still 200)
GET    /api/v1/channels/{channelId}/pins              → 200 PinsResponse
PinsResponse = { items: [{ messageId, pinnedBy, pinnedAt }] }            ← at most 5, so no cursor
pins_changed → { channelId, items: [...same...] }                       ← to the channel's room
```

| Test | Expected red |
|---|---|
| `test_pinning_twice_is_one_pin` | 404 (no route) |
| `test_a_channel_you_cannot_see_is_404` | 404 for the wrong reason: assert the Problem `detail`, so it fails until the route exists |
| `test_a_sixth_pin_is_409` · `test_a_tombstone_pin_is_409` | 404 |
| `test_deleting_a_message_unpins_it` | 404 on the `GET` |
| `test_pins_changed_reaches_the_room_only` | timeout waiting for the event |

> **Why:** a 404 is ambiguous before the route exists, because the tenancy test would pass
> vacuously. Saying how the test tells the two apart is what the reactions plan did
> (`02-message-reactions…:681-686`). Unpaginated is a decision the reviewer can see (`items` with
> no `nextCursor`), justified by the limit, so it is not a pagination rule broken silently.

## Task 3: The journey and the SPA's red (RED)

**Files:** `tests/bdd/features/pins.feature`, `steps/test_pin_steps.py`, `pages/chat_page.py`,
`PinnedList.test.tsx`, `usePins.test.ts`, and `useChannelSocket.test.ts`'s fake socket expectations

```gherkin
@bdd
Feature: Pinned messages
  Background:
    Given Ada is signed in

  Scenario: Grace sees the message Ada pins
    Given Grace is signed in and viewing #general
    When Ada pins "Standup moved to 10:00" in #general
    Then Grace sees "Standup moved to 10:00" in #general's pinned messages
```

- Reuse the scenario vocabulary's existing phrases verbatim
  (`docs/plans/ch06/gherkin/00-scenario-vocabulary.md`).
- New `data-testid`s (`pin-toggle`, `pinned-list`) live only in `ChatPage`. A step never contains a
  selector.
- Vitest: the list renders from `GET`; the toggle calls `PUT` or `DELETE`; a `pins_changed` event
  replaces the query cache; a response and its echo applied in either order give the same list.
  MSW stubs typed from the contract. Expected red: modules not found.

> **Why:** in ch06 the scenario review was the review that saved most time. Scenarios were written
> first, and never edited to fit the code (`ch06/02-…delivery-plan.md:133-158`). The page-object
> and vocabulary rules are what kept five parallel writers consistent
> (`04-slice-contracts.md:220-262`). One scenario, because the rules are proven lower down.

## Task 4: The table and the rules (GREEN)

**Files:** `models.py`, `alembic/versions/0005_pins.py`, `pins.py`

```python
# 0005_pins.py — the primary key is the idempotency; the index is the limit check.
op.create_table(
    "channel_pins",
    sa.Column("channel_id", sa.Uuid, sa.ForeignKey("channels.id"), nullable=False),
    sa.Column("message_id", sa.Uuid, sa.ForeignKey("messages.id"), nullable=False),
    sa.Column("pinned_by", sa.Uuid, nullable=False),  # Auth's user: no FK (Conventions §2)
    sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint("channel_id", "message_id"),
)
```

- [ ] Model, migration, then `pins.py` to Task 1's interface. Run Task 1's tests: 4 passed.
- [ ] `add` uses `ON CONFLICT DO NOTHING`, and counts and inserts in one transaction under `SELECT …
  FOR UPDATE` on the channel row, so two concurrent sixth pins cannot both succeed.
- [ ] Leave uncommitted.

> **Why:** code appears where the reason *is* the value: the key, the missing FK and the lock.
> The rest is a checklist over an interface that is already pinned down. The ~150-line plans
> worked this way and matched their diffs (`10-test-report…`: 9 files, 1 unnamed).

## Task 5: The routes and the broadcast (GREEN)

- [ ] `routers/pins.py` to Task 2's contract. Register it in `main.py`.
- [ ] Message delete (`routers/messages.py`) removes the pin in the same transaction, and publishes
  `pins_changed` after commit.
- [ ] `realtime.publish_pins_changed(channel_id, items)`.
- [ ] Regenerate: `python -m messaging.openapi > src/frontend/openapi/messaging.json`, then `npm run
  generate:api`. Task 2 passes: 6 passed. Messaging integration: 217 or more passed.
- [ ] Leave uncommitted.

## Task 6: The SPA (GREEN)

- [ ] `usePins` (TanStack Query; never a copy in Zustand, D24), `PinnedList` in `ChannelHeader`,
  and a pin toggle in `MessageItem`'s menu.
- [ ] `useChannelSocket` routes `pins_changed` into the cache.
- [ ] Task 3's Vitest passes, and `tsc` is clean. The journey runs in Task 8.
- [ ] Leave uncommitted.

## Task 7: The record

- [ ] Register: D43, 🟢, in the Messaging table.
- [ ] ADR with the `adr-writer` skill: the table over a column, and the whole-list broadcast.
- [ ] Doc 02: the three routes in §3.1, `pins_changed` in §3.2, `channel_pins` in §4, and the unpin
  path corrected (see *Corrections*).
- [ ] Sweep: `grep -rn "pin" docs/design src/services/messaging/messaging` for anything that says
  pins don't exist.

> **Why:** record a decision in the slice that makes it (CLAUDE.md, `ch06/02-…:53-57`), and sweep
> for the stale references it leaves (`e65e413`).

## Task 8: Verification

- [ ] `scripts/test.sh lint unit integration`, then `scripts/test.sh e2e`: green, counts at or
  above the baseline. Each layer once: the whole e2e layer is the journey's first run, and
  `-- -k pins` is for iterating if it fails.
- [ ] `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)`, **and**
  `.claude/hooks/security.sh`: semgrep and gitleaks as well. A waiver names every checker that fires
  on its line.
- [ ] **First real run**, on the Compose stack: `docker compose up -d --build`. Then:
  1. Pin in one browser, and watch the list change in a second.
  2. Pin a sixth message, and read the message you get.
  3. Delete a pinned message.

  Expect this run to find something the tests didn't. Fix it with a test, and record it below.
- [ ] If a sibling branch merged while this was in flight, merge `main` and rerun all of the above.
- [ ] Fill in *Found while building*. Leave the worktree dirty and report.

> **Why:**
> - Name the layers the change can reach, and no others: `integration` here because a service's
>   SQL changes; an SPA-only plan names `lint unit` and `e2e`. A filtered e2e run followed by the
>   whole layer builds the test stack twice.
> - A plan checked only by render and lint shipped a KEDA address bug, found at the next branch's
>   first deploy (`01-build-deploy-test-scripts-design.md:239`).
> - Portable deployment's live run found a Socket.IO rejection in two files its map never named
>   (`5d68b59`).
> - A CH006 waiver without its `nosemgrep` needed a branch of its own (`2374d95`).
> - Merged siblings broke a clean merge (`ff29137`).

## Found while building

*Filled in by the code-writer: every deviation from this plan, and every bug the first real run
found, each with the test that now pins it down. Empty until then.*

> **Why:** portable deployment's CORS fix is recorded only in a commit message (`5d68b59`), and
> squash-style commits hide the order of events. The plan is the only record that survives, so it
> is kept up (`10-test-report…:141` is the good version).

## Not in this plan

- Who pinned what, shown to other users beyond `pinnedBy` — the same privacy question reactions
  left open.
- Reordering pins by hand.

## Self-review

- **Issue coverage:** requirement 1 → Tasks 2, 5; 2 → Tasks 1, 4, 5; 3 → Tasks 1, 2, 5; the live
  list → Tasks 2, 3, 5, 6.
- **Names:** `pins_changed` everywhere, never `pin_changed`. `PinsResponse.items` matches the
  event's `items`.
- **Known ripple:** `useChannelSocket`'s existing tests, changed in Task 3: no GREEN task may
  write a test, so a test the change breaks or weakens is RED work (issue-4, issue-5, gh-3).
