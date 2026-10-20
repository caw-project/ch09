# Display names are unique across CollabHub, compared by a case-folded key

- **Status:** Accepted
- **Date:** 2026-10-20

## Context

Anyone could rename themselves to anyone's name, so a message could be passed off as
someone else's. Issue gh-3 lets a user change their own display name, which makes that
impersonation one request away. Making names unique raises two questions: across what, and
compared how.

## Decision

Names are unique across **all of CollabHub**, not per workspace, and **deleted accounts
count**: a deleted user keeps holding their name. This crosses the tenancy convention on
purpose (Conventions §5.4): a `409` from `PATCH /users/me` tells the caller that a name
exists in some workspace they cannot see. Revealing that a name exists was judged better than
allowing impersonation. The body names nobody and no workspace, and is identical whether the
holder is in the caller's workspace or not.

A name is stored trimmed and NFC-normalised, 1 to 100 code points, with control, format,
surrogate, private-use, unassigned, separator and default-ignorable characters refused.
Names are compared by `users.display_name_key`, `NFC(casefold(NFC(name)))`, computed by
`auth/names.py` and set by the `User` model on every assignment, under a plain unique index.
Postgres therefore compares bytes and never its own `lower()`, which follows `LC_CTYPE` and is
not full case folding (`Straße` and `STRASSE`). A rename is decided by the index, not a
pre-check; a first sign-in tries `X`, `X 2`, `X 3`, … each in a SAVEPOINT. Migration 0002 trims
and normalises every stored name and renames every duplicate but the oldest account, a
one-way data change.

## Consequences

The 409 is a deliberate, bounded leak of one bit — a name is taken somewhere — and reviewers
should read it as decided. Lookalike characters (TR39 confusables, a Cyrillic "А") are a
known gap. The zero-width joiner and non-joiner are refused with the other default-ignorable
characters, which some Persian and Indic names and emoji sequences use. A deleted account's
name is never released.

## Alternatives Considered

### Unique per workspace

Names are global — one per user — so a per-workspace rule would not stop the same person
appearing under two names, and the check would need the workspaces of both accounts.

### A unique index on `lower(display_name)`

Depends on the database's locale and is not full case folding, so the application and the
database would disagree about whether two names are one.

### Allow duplicates and show the email

Does not stop impersonation in a message list, which shows only the name.
