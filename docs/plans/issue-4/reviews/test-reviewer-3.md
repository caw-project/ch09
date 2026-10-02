# Test review — issue 4, round 3: approved

This round gates the fixes to the code-writer's send-back (items A1–A4, B5, B6). All six are in place. The unit tests and both integration files I reran now pass, and nothing was loosened to get there.

## Responses checked

| Send-back item | Writer's response | Outcome |
|---|---|---|
| A1 `a_message` passes `attachments` | The `"attachments": []` line is dropped from `conftest.py` | Resolved (diff read) |
| A2 `_as_message` needs `attachments=[]` | Every call in `test_indexing.py` passes it (11 lines in, 7 out) | Resolved |
| A3 `RealtimeContext` needs `assets` | `test_realtime_server.py` passes `assets=None`; `test_read_markers.py` passes `assets=app.state.assets` | Resolved. The `type: ignore` still covers the `None`s. |
| A4 asset `_settings` lacks two required fields | `redis_cache_url` and `object_store_public_endpoint` added | Resolved |
| B5 `contype` comes back as bytes | `contype::text`, plus stripping `"` from definitions, because Postgres quotes `position` | Resolved, and the report's "unverified" is now verified. Details below. |
| B6 Garage refusal always carries `*` | `preflight` returns `(status, headers)`. Allowed: status below 300 and its own origin. Refused: not 2xx, and the header is not `http://evil.test`. | Resolved |
| C optional items | Left alone | Accepted. They are minor and go to the code pair. |

## What ran

- `uv run pytest src/services/messaging/tests/unit src/services/asset/tests/unit -q`: **157 passed**.
- `uv run pytest src/services/testkit/tests/integration/test_garage.py src/services/messaging/tests/integration/test_schema.py -q`: **17 passed** in 21 s. Docker was reachable this time, which is why the writer's unverified `"position"` fix can now be called verified.
- No sketch. The change only touches test plumbing and two assertions, which the real code now passes. A rework pass doesn't rerun sketches the change can't reach.

## Findings

None.

Notes on the two assertions that changed:

- `test_message_attachments_key_and_uniqueness` still pins the exact column set, `PRIMARY KEY (message_id, position)`, `UNIQUE (asset_id)`, a foreign key to `messages(id)` and no foreign key on `asset_id`. The quote-stripping applies to both sides of the comparison and doesn't loosen it. A migration missing the unique constraint or adding an Asset foreign key still fails.
- The CORS test keeps both halves. A bucket with no rules gives `*` on the allowed origin, so the first half fails. A bucket that allows every origin gives the evil origin a 2xx, so the second half fails. Garage's refusal is a 403 that carries `*`. So "not 2xx, header is not the evil origin" is the strictest assertion that a correct Garage can satisfy, and a browser rejects a non-2xx preflight.

## Left for later stages

Carried from earlier reviews, plus send-back item C:

- **Code-writer:** move `cancelAll()` and `useAttachmentStore.getState().reset()` into `test/setup.ts`'s `afterEach` (optional; each attachments file already resets).
- **Code-writer:** refresh the stale docstrings: `testkit/images.py:6-7`, `tests/bdd/conftest.py` ("five ports", now seven), `messaging/tests/integration/test_messages.py:56` ("skeleton").
- Earlier carry-overs that are now built (`putFile` abort, `URL_STALE_MS`, `up --wait`) are the code pair's to confirm. The green report says the journey passes.

## Checked and sound

- The existing Messaging and Asset unit tests pass again, and no assertion was removed or weakened. The diffs only add arguments and fields the new code requires.
- Only the files the send-back named changed, plus the red report's Review-responses section. The report matches the diff.
- Round 1 and round 2's *Checked and sound* still stand. Nothing they cover changed.
