# Exemplar issue

This is the model the **issue-writer** skill (`.claude/skills/issue-writer/`) follows, and the
standard a delivery issue is held to before `scripts/deliver.sh` takes it. It is the issue behind
`docs/plans/exemplar-implementation-plan.md` — *pin a message to a channel* — annotated with why
each part is there.

**The feature is not real. Do not build it, and do not copy its content:** copy its shape, and the
reasons. Every `> **Why:**` note records something a delivery found an issue was missing, with the
evidence. An issue you write carries no `Why` notes.

When a delivery teaches something new, add it here, in the section it belongs to, with its
citation. The richest evidence is the plan's *Decisions — taken in this plan* table and its
*Corrections to the issue*: each row there is something the issue left for the plan to guess.

---

Issue: 0

# Issue 0 — Pinned messages

## Summary

Anyone who can see a channel can pin a message in it. The channel header shows the pinned
messages, newest pin first, and everyone looking at the channel sees the list change live.

## Services touched

**Messaging and the SPA.** Read `docs/design/02-messaging-service.md` §3.1–§3.2 and §4, and
`docs/design/06-frontend-spa.md` §5.2.

## What exists already

- Messages, their soft delete and their tombstones (`messages.deleted_at`, doc 02 §3.1.4).
- The `message_updated` and `message_deleted` broadcasts to the channel's room; the SPA applies
  both to its history cache (`useChannelSocket.ts`).
- Reactions (`c02dcd7`) — the nearest template: a table keyed by channel and message, a
  whole-state broadcast, a cache writer applied from both the response and the echo.

> **Why:** issue 1's *What the backend already provides* gave every plan run the right shapes
> from the start: no plan invented an endpoint or a field. State what exists in the words the
> code uses — table, event and hook names — so the plan greps for them instead of guessing.

## Requirements

1. **Pin and unpin.** Anyone who can see the channel pins or unpins any non-deleted message in
   it, from the message's menu. Pinning a pinned message, or unpinning one that isn't, succeeds
   and changes nothing.
2. **At most 5 per channel.** A sixth pin is refused with a message that says why; nothing
   changes.
3. **Tombstones.** A deleted message can't be pinned. Deleting a pinned message unpins it.
4. **The list.** The channel header shows the pins, newest pin first, each with its message's
   current text and author.
5. **Live.** Everyone looking at the channel sees a pin, an unpin, or an unpin-by-delete land
   without a reload — including the person who made it, once, not twice.

> **Why:** each requirement is one rule, stated so a test can be named for it: "at most", "any",
> "once, not twice". Issue 1's R3 packed three rules and a failure policy into one paragraph, and
> its every clause became its own test row in the plan.

## Where the rules meet

For each pair of rules that touch the same state, what happens when both fire:

- **The limit and concurrency (R2, R1):** two people pinning the fifth and sixth message at the
  same instant — exactly one succeeds; the channel never holds six.
- **Delete and the list (R3, R5):** a delete that unpins broadcasts the new list as well as the
  delete; a client that sees the delete first shows a tombstone until the list lands, never a
  pinned tombstone for good.
- **The response and the echo (R5):** the pinner's own client gets the new list twice — from its
  request and from the broadcast — in either order. Both give the same list.
- **An edit and the list (R4):** a pinned message edited shows its new text in the list.

> **Why:** the first version of issue 1 lost most to two clear rules colliding. R4 (write the
> caches directly on read) and R5 (refetch the list on switch, poll, focus and reconnect) each
> read well; together a refetch in flight put the stale count back. It was the plan-reviewer's
> first finding, and it took the plan three rounds and a new mechanism to settle
> (`docs/plans/ch08/03-code-pair-handoff.md`, *Evidence the exemplar issue cites*). Nothing in
> the issue said the two met. The rewritten issue 1 still missed one pair — a refused read
> and a reconnect — which only the code-reviewer's probe found.

## Paths each rule holds on

Every rule above holds on each of these, and *Acceptance* checks the unusual ones:

| Path | What must be true |
|---|---|
| First load of a channel | the list comes from the server |
| Return to a channel whose list is cached | the list shown is refreshed, not the cached one; a pin made while away appears |
| Switching channel while a pin request is in flight | the response lands in the right channel's list, or nowhere |
| Reconnect after a dropped socket | broadcasts missed while down are recovered by a refetch |
| A second tab or device of the same user | sees the pin live, like anyone else |
| Losing access to a private channel | the list goes with the channel; nothing leaks through a cached list |

> **Why:** the bug that got furthest in issue 1 was a rule on a path the issue never walked. R2
> ("scrolled to within 80px of the bottom") broke on a switch to a channel whose history was
> cached: the plan reset "at bottom" on a switch without checking anything scrolled there. The
> plan, the tests, four builds and three of four first code reviews all missed it
> (`docs/plans/ch08/03-code-pair-handoff.md`). The issue's *Acceptance* covered the first visit
> and scrolling back, not the return.

## What this assumes — check before building on it

Behaviour of the code or a library the requirements lean on, stated as an assumption for the
plan to check, not as a fact:

- **A broadcast sent before a join is acknowledged never reaches the joiner**, and the SPA
  refetches on the ack to cover the gap (`useChannelSocket.ts`, its header). The pinned list
  needs the same refetch, or a pin made in that gap is missing until the next one.
- **`ON CONFLICT DO NOTHING` makes a repeat pin a no-op** only with a unique key on
  `(channel_id, message_id)`.
- **TanStack Query's `setQueryData` on an absent key creates the entry** unless the writer
  guards it; the reactions writer does (`useMessages.ts`).

> **Why:** the first version of issue 1 said "refetch on window focus", which read as
> TanStack's `refetchOnWindowFocus`. In TanStack 5 that listens to tab visibility only, so an
> alt-tab back to a visible window never fired it (the same handoff, same section). An assumption named as
> one gets checked by the plan; one stated as fact gets built on.

## Timing

There is no throttle or window in this issue. The one ordering that matters, as a timeline:

```
t0  Ada pins M          → her request is in flight
t1  pins_changed [M]    → reaches Grace and Ada
t2  Ada's response [M]  → Ada applies it; her list is unchanged
    (t1 and t2 may land in either order; the list is the same)
```

> **Why:** issue 1 said "throttled to one per second; the latest id when the window ends" in
> one paragraph and "trailing edge" in another. Every plan run read that as leading *and*
> trailing (`docs/plans/ch08/01-delivery-team-handoff.md`), and the first tests passed a debounce
> the words didn't rule out (`docs/plans/ch08/02-test-pair-handoff.md`). A
> timeline — a request at t=0 and t=500, the send at t=1000 — settles leading, trailing and
> debounce in three lines.

## Decided already

1. Scope is R1–R5. Everything in *Not in this issue* stays out.
2. Anyone who can see the channel may pin — no role check.
3. At most 5 pins per channel; the sixth is refused.
4. A tombstone can't be pinned, and a delete unpins.
5. No register entry covers pins yet, and this work depends on no 🔴 one. The nearest is
   **D16** (tombstone retention): untouched, because a pin is removed on delete, not on purge.

Left to the plan, on purpose: where a pin is stored, the status code for the sixth pin, and
what the broadcast carries.

> **Why:** a question the author has already answered, written down, is one the plan doesn't
> spend a decision row on — these five are the exemplar plan's *Decided by the issue* rows.
> Saying what is left to the plan on purpose tells the plan-reviewer those rows are the plan's
> to take, not the issue's to have missed. Naming the nearest 🔴 entry and why it isn't touched
> is what the plan-reviewer checks first.

## Tests

- **Vitest and pytest below the journey**: the limit, the tombstone rule, idempotency, the
  concurrent sixth pin, 404 for a channel the caller can't see, the room-only broadcast, the
  response and echo in both orders.
- **One BDD journey**: Ada pins a message in #general; Grace, already looking at #general, sees
  it in the pinned list without reloading.

> **Why:** the issue names the layers and the one journey; the plan names each test. A
> journey that creates several things in a row exercises harness paths no earlier journey has
> — issue 1's first journey to create three channels hit a race in the page object that nobody
> could see until the code-writer ran it.

## Record in this slice

- Doc 02: the three routes, `pins_changed`, the `channel_pins` table.
- Register: a new entry for pins, 🟢 once built.
- An ADR: a table rather than a column, and the whole-list broadcast.

## Not in this issue

- Reordering pins by hand.
- Who pinned what, shown to other users beyond `pinnedBy`.
- A pin limit that varies by channel.

## Acceptance — on the branch's preview

With Ada and Grace in two browsers. Each check fails on `main`, which has no pins, and each
makes its own channel, so none needs a fresh preview:
- Ada pins a message; Grace's header shows it at once. Ada's shows it once.
- Ada pins a sixth; she reads why it was refused.
- Grace leaves #general, Ada pins another, Grace comes back: the new pin is there.
- Ada deletes a pinned message: it leaves both lists.

> **Why:** the first real run is where issue 1 expected to find what the tests didn't. Put the
> unusual paths from *Paths each rule holds on* here — the return, the second tab — or the run
> checks only what the tests already proved.

> **Why each check says what makes it fail without the change:** the acceptance-reviewer turns
> every check into a browser test on the branch's preview, and a test that passes on `main`
> proves nothing about the branch. Issue 7's three checks all passed on its preview, but two
> passed on `main` as well: "Grace is listed by name" and "after a reconnect nothing shows a
> short id" ran after the first check had already made Grace known to Ada's page, so the bug
> never had a stale directory to show. Only a rerun against `main` found it
> (`docs/plans/ch09/03-acceptance-reviewer-handoff.md`). For each check, name the starting
> state that leaves only the change to decide it. If that state is spent by running the check
> — a first sign-in, an empty workspace — say so, and name a different user for each check
> that needs one: a preview keeps its data between runs.

## References

- `docs/design/02-messaging-service.md` §3.1, §3.2, §4
- `docs/design/06-frontend-spa.md` §5.2
- Commit `c02dcd7` (message reactions) — the template for a whole-state broadcast and its cache
  writer
