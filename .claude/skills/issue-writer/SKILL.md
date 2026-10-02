---
name: issue-writer
description: Write a delivery issue — docs/issues/NNN.md for scripts/deliver.sh — by grilling the user against the exemplar issue. Use when the user wants to write, draft or spec an issue for delivery, or turn a feature idea into one.
---

# Issue writer

The issue is the whole spec `scripts/deliver.sh` gives its six agents, and nobody is there to
answer a question mid-run. A good one leaves no stage stopping for a human over the spec, and
every stage reading it the same way. Past issues were clear rule by rule and still cost rounds
where the rules **meet**, on **paths** nobody walked, on **assumptions** stated as facts, and on
timing described in words instead of a **timeline**. Those four are this skill's leading words.

The interview itself is **grilling**, as written: this skill doesn't restate its method. What it
adds is aimed at the one reader the issue has — agents that can't ask a follow-up: the facts
gathered first, four branches every requirement must visit, an end you can check, the issue's
shape, and a read-back as the plan-writer.

## 1. Read the exemplar

Read `docs/issues/exemplar-issue.md` in full. Its sections are the issue's shape, and its
`Why` notes are what past deliveries found missing — the reason for each section. Read
`CLAUDE.md` and `docs/design/07-open-decisions-register.md` too: an issue answers to both.

Done when you can name each section of the exemplar and what went wrong without it.

## 2. Gather the facts

Facts are yours to find, never the user's to supply. From the user's idea, dispatch `Explore`
sub-agents for what the issue will need, and carry on with step 3 while they run:

- the design doc of every service the work touches, and the sections it changes;
- what already exists, in the code's own names — tables, routes, events, hooks, helpers;
- the register entries nearest the work, 🔴 ones above all;
- the nearest past feature to use as a template (a commit), and sibling branches in flight.

Done when every fact the issue will state has a source you can cite.

## 3. Grill

Invoke `mattpocock-skills:grilling` with the Skill tool if it is listed; if not, read
`grilling.md` beside this file — the same skill, vendored — and follow it. Everything it says
holds here, its rule above all that the decisions are the user's: put each to them and wait.
This step adds to its design tree, and to when it is done.

**Four branches hang off every requirement**, however settled it looks — past issues were
clearest exactly where they went wrong. They are questions to put, never answers to supply:
each one asked, with your recommendation, and answered by the user.

- **Meet** — each other rule that touches the same state. When both fire at once, or one
  lands while the other is in flight, what does the user see?
- **Paths** — the rule on each path through the app: first load, a return to something
  cached, a switch while a request is in flight, a reconnect, a second tab or device, lost
  access, an unmount. What must be true on each?
- **Assumptions** — the behaviour of the existing code or a library the rule leans on. These
  are facts, so they are yours: check each by sub-agent against the code and the installed
  source. What you can't confirm goes into the issue labelled as an assumption for the plan
  to check.
- **Timeline** — anything with time or order in it (a throttle, a window, a retry, a
  response racing a broadcast) gets a worked sequence: `t=0 … t=500 … t=1000`, what is
  sent and what is seen.

**And for the issue as a whole:** what is decided already, what is left to the plan on
purpose, what is not in this issue, and the first real run's checks. A 🔴 register entry the
work depends on can't be built on: put it to the user as a decision to make first, or cut it
from scope.

**Done** when grilling is — the frontier empty, and the user confirming you share an
understanding — and a coverage table, every requirement against Meet, Paths, Assumptions and
Timeline, has each cell answered or marked "n/a" with the reason. Show the table with that
confirmation, and write nothing until the user gives it.

## 4. Write the issue

- **Where:** `docs/issues/<NNN>.md`, the next number after the highest there (the exemplar is
  0). Its first line is `Issue: <N>`, which `scripts/deliver.sh` reads. It is a change to the
  repo, so it goes on a branch in a worktree, as `CLAUDE.md` says; nothing is committed.
- **Shape:** the exemplar's sections, in its order, without its `Why` notes. A section left out
  is left out on purpose — say why in one line where it would have been.
- **Requirements:** numbered, one rule each, in words a test can be named from: "at most",
  "any", "once, not twice", "the latest". Where the rules meet, the paths table, the
  assumptions and the timelines are sections of their own, as in the exemplar.
- **Length:** 120–250 lines. The agents read all of it; what they need to work out for
  themselves, they will.

## 5. Check it

Read the issue once as the plan-writer will, with no memory of the grilling:

- every exemplar section present, or its absence explained;
- every `Why` in the exemplar answered by something in this issue;
- no sentence two plan runs could read two ways. Each one you find goes back to the user as
  a question, and the issue is rewritten with the answer.

Then give the user the path and the command that starts delivery,
`scripts/deliver.sh docs/issues/<NNN>.md`, and stop — starting the delivery is theirs.
