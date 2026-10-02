# Send-back from the code-writer — issue 4

The code is built and every GREEN task is in place; what fails is **test files that the
plan assigned to Task 5/6 as "modify" but that a code-writer may not write**, plus two tests that
no correct build can pass. Nothing here is a production fault. Each item is the smallest change.

## A. Existing tests the new code legitimately breaks (plan Task 5/6 "modify" rows)

| # | File | What it printed | Why no code fixes it | Smallest fix |
|---|---|---|---|---|
| 1 | `messaging/tests/unit/conftest.py:39` (`a_message`) | `TypeError: 'attachments' is an invalid keyword argument for Message` — 18 tests: `test_message_policy.py` (8), `test_indexing.py` (6), `test_attachments.py` (4) | Decided 5 drops `messages.attachments`; the model cannot accept the key | delete the `"attachments": [],` line |
| 2 | `messaging/tests/unit/test_indexing.py` — 6 `_as_message(…, reactions=[])` calls | `TypeError: missing keyword-only argument 'attachments'` | the plan makes `attachments` required beside `reactions` ("a default would make a forgotten aggregate look like nothing attached") | add `attachments=[]` to each |
| 3 | `messaging/tests/unit/test_read_markers.py` and `test_realtime_server.py:35` (`RealtimeContext(settings=…, sessions=None, security=None, jobs=None)`) | `TypeError: RealtimeContext.__init__() missing 1 required positional argument: 'assets'` — 3 tests | the plan gives `RealtimeContext` a required `assets: AssetClient` | add `assets=None` (they already pass `None` for the others, with the same `type: ignore`) |
| 4 | `asset/tests/unit/test_health.py::_settings` | `ValidationError: redis_cache_url, object_store_public_endpoint — Field required` — 2 tests | both are required settings (plan Task 5, decision 19/22) | add `redis_cache_url="redis://redis-cache:6379/0"` and `object_store_public_endpoint="http://localhost:3900"` |

## B. Tests no correct build can pass

5. **`messaging/tests/integration/test_schema.py::test_message_attachments_key_and_uniqueness`**
   (line 221). It selects `contype` and compares `("p", …)`; asyncpg returns Postgres's `"char"`
   type as **bytes**, so the set holds `(b'p', 'PRIMARY KEY (message_id, position)')` and
   `kind == "f"` is never true either. Printed: `assert ('p', 'PRIMARY KEY (message_id, position)')
   in {(b'f', 'FOREIGN KEY …'), (b'n', …), …}`. The migration is right (the set shows the real
   constraints). Fix: `SELECT contype::text, pg_get_constraintdef(oid)`.
6. **`testkit/tests/integration/test_garage.py::test_cors_preflight_allows_only_the_app_origin`**
   (line 77). With the bootstrap's rules in place the allowed origin now gets
   `access-control-allow-origin: http://spa.test` (first half passes). The refused origin gets a
   Garage **403 XML error** — headers `content-type: application/xml`, `content-length: 211` — and
   Garage puts `access-control-allow-origin: *` on its error responses, so
   `assert "access-control-allow-origin" not in preflight("http://evil.test")` fails for every
   build: no CORS rule set, however strict, makes Garage's refusal header-free. A browser still
   refuses it (a preflight must be 2xx). Fix: have `preflight` return the status too, and assert the
   evil preflight is **not 2xx** (it is 403) and its `access-control-allow-origin` is not
   `http://evil.test`; the first half already carries the positive. (Run: `uv run pytest
   src/services/testkit/tests/integration/test_garage.py` — 1 passed, 1 failed on this line only.)

## C. Optional, for the test pair's tidiness (not blocking)

* `src/frontend/src/test/setup.ts`: red report asked for `cancelAll()` + `useAttachmentStore.getState().reset()`
  in the global `afterEach` once the store exists. It exists now; each attachments test file already
  resets, so nothing fails without it.
* Stale docstrings in test files: `testkit/images.py:6-7`, `tests/bdd/conftest.py` ("five ports", now seven),
  `messaging/tests/integration/test_messages.py:56` ("the Asset service is a skeleton").

## What is verified meanwhile

Vitest 329/329, typecheck, ESLint and `vite build` clean; `scripts/test.sh lint` passes;
Asset integration (all 28) and Garage `test_the_bootstrap…` pass; Messaging integration (the whole
directory including `test_attachments.py`) passed before the table-contype fix above is needed; the
only unit/integration reds are items 1–6. **The journey now runs and passes**: after
the human's answer, `scripts/test.sh` uses a per-worktree Compose project and `down -v` before `up`;
the whole e2e layer is 21 passed (one flaky "stream recovers" scenario passed on rerun). Items 1–6
above are the only reds left (unit 23, integration `test_schema` contype and Garage evil-origin;
Elasticsearch-backed integration tests time out here, files untouched).
