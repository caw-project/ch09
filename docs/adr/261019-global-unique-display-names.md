# Display names are unique across CollabHub, keyed in the application

- **Status:** Accepted
- **Date:** 2026-10-19

## Context

A person can now rename themselves (issue gh-3). If names could repeat, anyone could take the name of a colleague and be mistaken for them in a message list. Auth's tenancy is by workspace, but a user belongs to many, and their name is one name in all of them.

## Decision

Display names are unique across the whole installation, ignoring case, and a deleted account's name stays taken (register D46). Uniqueness is enforced by a non-partial unique index `ux_users_display_name_key` over a `display_name_key` column, not by a lookup. The key is `NFC(name.casefold())`, computed in Python by `auth.names.name_key` and set by a validator on `User.display_name`, so every write carries its key. The stored name is trimmed and NFC-composed; length (1–100) is counted in code points of that form, and control, format, surrogate, private-use, unassigned, line/paragraph-separator and default-ignorable characters are refused.

A rename that loses the index gets a 409 `"That name is already taken."` naming no user and no workspace. A first sign-in never refuses: it takes `X`, `X 2`, `X 3`, … each insert in its own savepoint. Migration `0002` trims and composes stored names, keeps the oldest holder of each key and suffixes the rest, then builds the index; it is one-way.

## Consequences

The index is the whole concurrency story: two writers racing for one name cannot both win, with no lock and no pre-check. The 409 reveals that a name exists *somewhere* in CollabHub, including in a workspace the caller cannot see — a deliberate exception to Conventions §5.4's habit of not confirming existence, documented there. Names are a shared namespace, so a name cannot be reused after its owner leaves. Lookalike characters (Cyrillic `а` for Latin `a`) are not handled.

Because the key is computed in the application, the database compares bytes and cannot disagree with Python; a change to the folding rule means recomputing the keys in a migration.

## Alternatives Considered

### An expression index on `lower(display_name)`

Postgres `lower()` follows the database's ctype and provider, which differ between the Compose image, testcontainers and a managed Postgres, so the application and database could disagree. It also does not fold `ß`.

### Unique per workspace

A name is global, so per-workspace uniqueness would let the same person be two names, and two people one name in a shared workspace.

### A check before writing

Races between check and write; the index is needed anyway.
