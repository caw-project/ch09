# Display names are unique across CollabHub, compared by a stored key

- **Status:** Accepted
- **Date:** 2026-10-17

## Context

Issue gh-3 lets a user rename themselves. Two people with the same name make a message list ambiguous and invite impersonation, so the issue asks for uniqueness, ignoring case, across all of CollabHub rather than per workspace. Names also had no rules at all: anything up to 100 characters, including invisible ones, untrimmed. The comparison has to agree between the rename route, a first sign-in and a data migration, and it must hold under concurrent writes.

## Decision

A display name is one per user and unique across all of CollabHub, deleted accounts included (register D46). Every rule lives in `auth/names.py`: names are trimmed and composed to NFC, 1–100 code points, and refuse control, format, surrogate, private-use, unassigned and separator characters and the Default_Ignorable_Code_Point ranges.

Names are compared by a key, `NFC(casefold(name))`, computed once in Python and stored in `users.display_name_key` under a plain unique index `ux_users_display_name_key`. Full case folding means `Strauß` and `STRAUSS` collide, which `lower()` would miss. The index, not a pre-check, is the race control: the loser of a concurrent rename gets a 409 (`That name is already taken.`, naming nobody), and the loser of a concurrent first sign-in retries with the next free suffix (`X 2`, `X 3`). Sign-in is never refused over a name. Migration `0002` tidies existing names and renames duplicates with the same code; the oldest account of each key keeps its name.

Deleted accounts keep their names taken. That is a third documented exception to the soft-delete rule (Conventions §3), and the 409 can reveal that a name exists in another workspace (Conventions §5.4); it reveals nothing else.

## Consequences

The database compares exactly what the application computed, so there is no second case rule to drift. Lookalike characters (Cyrillic `а` for Latin `a`) are not detected, and a name can be at most 100 code points rather than graphemes. A deleted person's name is never reusable. Changing the case rule later is one function plus a migration that recomputes the key and re-runs the dedupe. Length is counted in code points on both the server and the SPA's Save gating.

## Alternatives Considered

### A functional index on `lower(display_name)`

Puts a second, different case rule in Postgres, and `lower()` leaves `ß`/`ss` and final sigma distinct.

### A check-then-write in the route

Cannot see another transaction's uncommitted name, so two renames to one name both succeed.

### Unique per workspace

Users belong to many workspaces and a name is global to the person, so a per-workspace rule would need a name per membership.
