# Issue #4 — questions for a human

## code-writer stopped, round 1 — e2e test stack

The run stopped twice over: the e2e layer could not bring the test stack up, and the
stage edited `CLAUDE.md`, which no stage may write — the workflow refused it and
stopped. That edit has been reverted; leave `CLAUDE.md` alone and list anything it
should say under *Left for the human* in your report.

1. Why does the e2e test stack fail to come up, and what should this stage do about it?

   **Answer:** The cause is the test stack, not this issue's code. Every worktree runs
   `scripts/test.sh e2e` under the one Compose project `collabhub-test`, so they share one
   `collabhub-test_postgres-data` volume. Another worktree's e2e run left Messaging's
   database at its own Alembic revision 0005, which this branch doesn't have, so
   Messaging's migration fails at start and the container never goes healthy (or, on a
   branch with its own 0005, the new tables are never created).

   Fix it in `scripts/test.sh` as part of this stage — `scripts/` is yours to write:

   - Give the e2e stack a project name of its own per worktree: `collabhub-test-` plus the
     repo root's directory name (`caw-issue-2` → `collabhub-test-caw-issue-2`), passed as
     `-p` on every `docker compose` call the e2e layer makes (`E2E_COMPOSE`), including the
     teardown and its `docker compose -p … ps` hint. Put the name in one variable.
   - At the start of the layer, after taking the lock and before `up`, run `down -v
     --remove-orphans` for that project, so every run starts from empty volumes and a
     fresh migration. Keep the teardown at the end as it is.
   - Keep the machine-wide lock: the host ports are still fixed, so two worktrees still
     can't run the stack at once. Update the comments that say the project name is fixed
     and that the volume is kept between runs.
   - `docker-compose.test.yml`'s `name: collabhub-test` stays as the default for anyone
     running Compose by hand; `-p` overrides it. Correct its comment if it says otherwise.

   Then run `scripts/test.sh e2e` as before. The old `collabhub-test_*` volumes are left
   for the human to remove.

   Your previous pass built every GREEN task, and its send-back, `reviews/code-writer-sendback-3.md`, still stands: the test-file faults in it are the test-writer's to fix. Make the script change, run the e2e layer, and send back as before, adding anything the journey shows.
