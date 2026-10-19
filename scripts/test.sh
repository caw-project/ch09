#!/usr/bin/env bash
# Run CollabHub's checks. Developers and CI run this same script.
#
#   scripts/test.sh                    lint, unit, then integration
#   scripts/test.sh lint unit          only these layers, in this order
#   scripts/test.sh unit -- -x -k auth anything after -- goes to pytest
#   scripts/test.sh all                every layer, e2e included — what CI runs
#   scripts/test.sh e2e -- --headed -k channels
#
#   lint         ruff, the CollabHub convention checks, actionlint, eslint, tsc, helm lint
#   unit         pytest, then Vitest for the SPA — no Docker, no network
#                (arguments after -- go to pytest only)
#   integration  pytest against real containers — needs Docker
#   e2e          the Gherkin journeys in tests/bdd, in a real browser, against
#                the throwaway test stack it brings up and takes down — needs
#                Docker and .env. Not in the default run, because it is slow.
#
#   KEEP_STACK=1 leaves the e2e test stack running afterwards, for iterating on
#                steps. See "Acceptance tests" in README.md.
#
# After every layer, pass or fail, the run rewrites docs/test-report.md — the
# committed report of what each layer last did. Each tool writes its results into
# build/test-results/ and testkit.report merges them; a layer that did not run
# this time keeps its last result there, flagged if it is from another revision.
#
set -euo pipefail
# shellcheck source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

layers=()
pytest_args=()
while [ $# -gt 0 ]; do
    case "$1" in
        lint | unit | integration | e2e) layers+=("$1") ;;
        all) layers+=(lint unit integration e2e) ;;
        --)
            shift
            pytest_args=("$@")
            break
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *) die "unknown layer '$1' (expected lint, unit, integration, e2e or all)" ;;
    esac
    shift
done
[ ${#layers[@]} -gt 0 ] || layers=(lint unit integration)

require_cmd uv
cd "$REPO_ROOT"

RESULTS_DIR="$REPO_ROOT/build/test-results"
REPORT=docs/test-report.md

# The revision the report describes. Like IMAGE_TAG, plus -dirty for uncommitted
# changes — except to the report itself, or a second run before a commit would
# call a clean tree dirty.
REPORT_REVISION="$(git rev-parse --short=12 HEAD)"
if [ -n "$(git status --porcelain -- . ":(exclude)$REPORT")" ]; then
    REPORT_REVISION="${REPORT_REVISION}-dirty"
fi

ensure_node_modules() {
    # CI always installs clean. Locally an existing install is trusted — unless
    # the lockfile is newer than it, which is how a merge that added Vitest left
    # lint failing on packages that were never installed. npm rewrites
    # node_modules/.package-lock.json on every install, so it dates the install.
    local lock=src/frontend/package-lock.json
    local installed=src/frontend/node_modules/.package-lock.json
    if [ -n "${CI:-}" ] || [ ! -f "$installed" ] || [ "$lock" -nt "$installed" ]; then
        log "installing frontend dependencies"
        (cd src/frontend && npm ci)
    fi
}

# Every credential charts/collabhub-deps renders, as a --set-string argument.
# The values are only shaped right; the render never contacts anything.
DEPS_TEST_CREDENTIALS=(
    --set-string postgres.password=lint-password
    --set-string garage.adminToken=lint-admin-token
    --set-string garage.rpcSecret=0000000000000000000000000000000000000000000000000000000000000002
    --set-string garage.accessKeyId=GK000000000000000000000002
    --set-string garage.secretAccessKey=0000000000000000000000000000000000000000000000000000000000000002
    --set-string dex.clientSecret=lint-client-secret
    --set-string 'dex.passwordHash=$2b$10$lintlintlintlintlintlO0000000000000000000000000000000'
    --set-string workerClientSecret=lint-worker-secret
    --set-string messagingClientSecret=lint-messaging-secret
)

layer_lint() {
    require_cmd npm helm git python3

    log "lint: ruff"
    uv run ruff check .
    uv run ruff format --check .

    log "lint: CollabHub conventions"
    # With no arguments conventions.py checks only what differs from HEAD, which
    # in a CI checkout is nothing — so hand it every tracked Python file.
    git ls-files -z '*.py' | xargs -0 python3 .claude/hooks/checks/conventions.py

    log "lint: workflows"
    # actionlint runs shellcheck over every `run:` block when it finds it on PATH. Both
    # come from PyPI wheels through uvx, so nothing is installed for them.
    uvx --quiet --from actionlint-py==1.7.12.25 --with shellcheck-py==0.11.0.1 actionlint

    log "lint: frontend"
    ensure_node_modules
    (cd src/frontend && npm run --silent lint && npm run --silent typecheck)

    log "lint: helm"
    # values.yaml leaves the NetworkPolicy peers to each environment and fails the
    # render without them, and `helm lint` cannot be told the KEDA API exists. So
    # the defaults lint with both of those off, the k3d values lint with
    # autoscaling off, and the k3d values render once more with the KEDA API
    # declared, so the ScaledObjects are checked too.
    helm lint --quiet charts/collabhub \
        --set networkPolicy.enabled=false \
        --set-string origin=http://localhost:8080 \
        --set components.worker.autoscaling.enabled=false
    helm lint --quiet charts/collabhub --values charts/collabhub/values-k3d.yaml \
        --set components.worker.autoscaling.enabled=false \
        --set-string origin=http://localhost:8080 \
        --set-string ingress.host=localhost
    helm template collabhub charts/collabhub --values charts/collabhub/values-k3d.yaml \
        --set-string origin=http://localhost:8080 \
        --set-string ingress.host=localhost \
        --api-versions keda.sh/v1alpha1 >/dev/null

    # The Ingress is an allow-list of public prefixes. Nothing internal may ever
    # be routed from it (Conventions §5.5), and it must always name a host — an
    # empty host matches every host, which is a collision once two instances
    # share a cluster. Only routed paths are checked: the template's comments
    # name the internal paths too, to say they are not routed.
    local ingress
    ingress="$(helm template collabhub charts/collabhub \
        --values charts/collabhub/values-k3d.yaml \
        --set-string origin=http://a.localhost:8080 \
        --set-string ingress.host=a.localhost \
        --api-versions keda.sh/v1alpha1 \
        --show-only templates/ingress.yaml)"
    if printf '%s\n' "$ingress" |
        grep -Eq '^[[:space:]]*(-[[:space:]]+)?path:[[:space:]]*"?(/api/v1/internal|/health)'; then
        die "charts/collabhub's Ingress routes an internal path"
    fi
    # Auth's service-token endpoint is under the public /api/v1/auth prefix, but
    # is for internal callers only (doc 01 §3.1). An Exact route sends it to the
    # SPA instead — Traefik and ingress-nginx both prefer Exact over Prefix. A
    # route runs from its `- path:` line to the next one.
    local token_route
    token_route="$(printf '%s\n' "$ingress" |
        awk '$1 == "-" && $2 == "path:" { inside = ($3 == "/api/v1/auth/service-token") } inside')"
    printf '%s\n' "$token_route" | grep -q 'pathType: Exact' &&
        printf '%s\n' "$token_route" | grep -q 'name: collabhub-frontend$' ||
        die "charts/collabhub's Ingress has no Exact route sending /api/v1/auth/service-token to the frontend Service, so its /api/v1/auth Prefix routes it to Auth"
    printf '%s\n' "$ingress" | grep -q 'host: "a.localhost"' \
        || die "charts/collabhub's Ingress does not route on its host"
    # The refusal has to be for the missing host: a render that fails for any
    # other reason would otherwise pass here.
    local refused
    if refused="$(helm template collabhub charts/collabhub \
        --values charts/collabhub/values-k3d.yaml \
        --set-string origin=http://a.localhost:8080 \
        --api-versions keda.sh/v1alpha1 2>&1 >/dev/null)"; then
        die "charts/collabhub rendered an enabled Ingress with no host"
    fi
    printf '%s\n' "$refused" | grep -qF 'ingress.host is empty' \
        || die "charts/collabhub failed to render with no ingress.host, but not because of it: $refused"

    local deps=(charts/collabhub-deps "${DEPS_CHART_FILES[@]}" --set-string origin=http://lab.example)
    helm lint --quiet "${deps[@]}" --values charts/collabhub-deps/values-k3d.yaml
    # No credential has a default, so the chart refuses to render without them —
    # it cannot be installed anywhere by accident with throwaway values (D41).
    # Helm stops at the first missing value, so each credential is left out in
    # turn with every other one supplied, and the refusal has to name that one:
    # a default crept back into any of them, or a render that fails for some
    # other reason, would otherwise pass here.
    local i j path others
    for ((i = 0; i < ${#DEPS_TEST_CREDENTIALS[@]}; i += 2)); do
        path="${DEPS_TEST_CREDENTIALS[i + 1]%%=*}"
        others=()
        for ((j = 0; j < ${#DEPS_TEST_CREDENTIALS[@]}; j += 2)); do
            [ "$j" -eq "$i" ] || others+=("${DEPS_TEST_CREDENTIALS[@]:j:2}")
        done
        if refused="$(helm template collabhub-deps "${deps[@]}" --set-string ingress.className=nginx \
            ${others[@]+"${others[@]}"} 2>&1 >/dev/null)"; then
            die "charts/collabhub-deps rendered with no $path"
        fi
        printf '%s\n' "$refused" | grep -qF "$path is empty: supply it" \
            || die "charts/collabhub-deps failed to render without $path, but not because of it: $refused"
    done
    # ...and every one of them can arrive on the command line, with no values file.
    helm template collabhub-deps "${deps[@]}" --set-string ingress.className=nginx \
        "${DEPS_TEST_CREDENTIALS[@]}" >/dev/null

    # The lab: ingress-nginx, plain HTTP, CollabHub bringing its own dependencies.
    helm lint --quiet charts/collabhub --values charts/collabhub/values-lab.yaml \
        --set-string origin=http://lab.example \
        --set-string ingress.host=lab.example \
        --set components.worker.autoscaling.enabled=false
    helm template collabhub charts/collabhub --values charts/collabhub/values-lab.yaml \
        --set-string origin=http://lab.example \
        --set-string ingress.host=lab.example \
        --api-versions keda.sh/v1alpha1 >/dev/null
    helm template collabhub-deps "${deps[@]}" --values charts/collabhub-deps/values-lab.yaml \
        "${DEPS_TEST_CREDENTIALS[@]}" >/dev/null
}

layer_unit() {
    # helm too: the chart checks under testkit render with it, and a skipped one
    # would read as green.
    require_cmd npm helm
    log "unit tests: pytest"
    uv run pytest -m unit --cov --cov-report=term:skip-covered \
        --cov-report="xml:$RESULTS_DIR/unit-python-coverage.xml" \
        --junitxml="$RESULTS_DIR/unit-python.xml" \
        ${pytest_args[@]+"${pytest_args[@]}"}

    log "unit tests: vitest"
    ensure_node_modules
    (cd src/frontend && npm run --silent test -- \
        --reporter=default --reporter=junit --outputFile.junit="$RESULTS_DIR/unit-frontend.xml" \
        --coverage.enabled --coverage.reporter=text-summary --coverage.reporter=cobertura \
        --coverage.reportsDirectory="$RESULTS_DIR/unit-frontend-coverage")
}

layer_integration() {
    require_cmd docker
    docker info >/dev/null 2>&1 || die "integration tests need Docker, and the daemon is not reachable"
    log "integration tests"
    uv run pytest -m integration --junitxml="$RESULTS_DIR/integration.xml" \
        ${pytest_args[@]+"${pytest_args[@]}"}
}

# The *test* stack, never the development one. The suite truncates the messaging
# tables before every scenario, so docker-compose.test.yml gives this stack its
# own volumes and host ports, and it runs alongside a development stack without
# touching it. The project name is per worktree (`collabhub-test-` plus the repo
# root's directory name, `-p` overriding the file's `name:`), so one worktree's
# database never carries another branch's Alembic revision into this run.
E2E_PROJECT="collabhub-test-$(basename "$REPO_ROOT" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9_\n-' '-')"
E2E_COMPOSE=(docker compose -p "$E2E_PROJECT" -f docker-compose.yml -f docker-compose.test.yml)

e2e_down() {
    log "e2e: taking the test stack down (KEEP_STACK=1 leaves it up)"
    # `down -v` at the start of a run empties the volumes; here a plain `down`
    # leaves them, so KEEP_STACK reruns and post-mortems still have the data.
    "${E2E_COMPOSE[@]}" down ||
        log "e2e: teardown failed — check 'docker compose -p $E2E_PROJECT ps'"
}

# One test stack per machine. Its host ports are fixed, so a run from a second
# worktree — two issues going through scripts/deliver.sh at once — would rebuild
# the stack under the first and take it down mid-scenario, even though the
# project names differ. The second waits instead. A lock whose run has gone is
# taken over.
E2E_LOCK="${TMPDIR:-/tmp}/collabhub-test-stack.lock"
E2E_LOCK_WAIT_SECONDS="${E2E_LOCK_WAIT_SECONDS:-3600}"

e2e_lock() {
    local holder waited=0
    until mkdir "$E2E_LOCK" 2>/dev/null; do
        holder="$(cat "$E2E_LOCK/pid" 2>/dev/null || true)"
        if [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; then
            log "e2e: taking the test stack over from run $holder, which has gone"
            rm -rf "$E2E_LOCK"
            continue
        fi
        [ "$waited" -gt 0 ] || log "e2e: another run (${holder:-starting}) has the test stack — waiting for it"
        [ "$waited" -lt "$E2E_LOCK_WAIT_SECONDS" ] ||
            die "e2e: waited ${waited}s for the test stack; remove $E2E_LOCK if no run holds it"
        sleep 5
        waited=$((waited + 5))
    done
    # $$ is the script's own pid, even in the subshell run_layer runs this in.
    echo "$$" >"$E2E_LOCK/pid"
}

# Runs when the script exits during the e2e layer — a failed `up`, a failed
# scenario, Ctrl-C, or the end of the run. It takes the exit status first and
# exits with it again, so the teardown can neither hide a failure nor invent one.
e2e_on_exit() {
    local status=$?
    trap - EXIT
    # A failed run's cause is usually in a container's log, which the teardown
    # is about to delete: print the tail of the ones a journey leans on first.
    if [ "$status" -ne 0 ]; then
        log "e2e: failed — the end of the Worker's and Messaging's logs"
        "${E2E_COMPOSE[@]}" logs --no-color --tail 40 worker messaging 2>&1 || true
    fi
    [ "${KEEP_STACK:-}" = 1 ] || e2e_down
    rm -rf "$E2E_LOCK"
    exit "$status"
}

layer_e2e() {
    require_cmd docker
    docker info >/dev/null 2>&1 || die "e2e tests need Docker, and the daemon is not reachable"
    [ -f .env ] ||
        die "e2e tests need .env at the repo root, which the Compose files read: cp .env.example .env"

    e2e_lock
    trap e2e_on_exit EXIT
    [ "${KEEP_STACK:-}" != 1 ] || log "e2e: KEEP_STACK=1 — the test stack stays up afterwards"

    # Empty volumes every run: a fresh Postgres and a fresh migration, whatever
    # an earlier run of this worktree left behind.
    log "e2e: removing any earlier test stack and its volumes ($E2E_PROJECT)"
    "${E2E_COMPOSE[@]}" down -v --remove-orphans

    log "e2e: bringing the test stack up"
    # --wait holds until every container with a healthcheck is healthy, and the
    # frontend has one for exactly this reason. The timeout turns a container that
    # never gets there into a failure rather than a hung run.
    "${E2E_COMPOSE[@]}" up -d --build --wait --wait-timeout 300

    log "e2e: installing Chromium for Playwright"
    uv run playwright install chromium

    log "e2e tests"
    # Pointed at tests/bdd so the run does not collect every service's tests only
    # to deselect them. Under `set -e` a failure exits here, through the trap —
    # and so does success, when the layer's subshell ends.
    uv run pytest tests/bdd -m bdd --junitxml="$RESULTS_DIR/e2e.xml" \
        ${pytest_args[@]+"${pytest_args[@]}"}
}

log "syncing the Python workspace"
# --all-packages, because a plain sync installs only the root's dev group, not
# each member's. Messaging's dev group is where the Socket.IO async client and
# aiohttp come from, and without them its real-time tests fail to connect.
uv sync --locked --all-packages --quiet

# Runs one layer and keeps its exit status, so the report is written whether it
# passed or not. The subshell is what keeps `set -e` working inside the layer: a
# function called as `layer || status=$?` would run with errexit silently off.
run_layer() {
    local layer="$1" status=0 args=()
    rm -rf "$RESULTS_DIR/$layer".json "$RESULTS_DIR/$layer".xml "$RESULTS_DIR/$layer"-*
    mkdir -p "$RESULTS_DIR"

    set +e
    (
        set -e
        "layer_$layer"
    )
    status=$?
    set -e

    # Lint takes no pytest arguments, so it cannot have been a filtered run.
    [ "$layer" = lint ] || args=(${pytest_args[@]+"${pytest_args[@]}"})
    # A report that fails to write must not turn a failed layer into a pass, or
    # a passed one into a failure.
    if uv run python -m testkit.report record "$layer" "$status" "$REPORT_REVISION" \
        --results "$RESULTS_DIR" -- ${args[@]+"${args[@]}"} &&
        uv run python -m testkit.report render --results "$RESULTS_DIR" \
            --out "$REPORT" --revision "$REPORT_REVISION"; then
        log "report: $REPORT"
    else
        log "report: could not write $REPORT"
    fi

    if [ "$status" -ne 0 ]; then
        log "failed: $layer — see $REPORT"
        exit "$status"
    fi
}

for layer in "${layers[@]}"; do
    run_layer "$layer"
done

log "passed: ${layers[*]}"
