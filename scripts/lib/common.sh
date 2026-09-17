# shellcheck shell=bash
# Shared by scripts/build.sh, deploy.sh and test.sh — sourced, never executed.
#
# Everything a CI pipeline might need to change is an environment variable with a
# local default, so the pipeline runs the same scripts a developer does and
# overrides only these:
#
#   IMAGE_REGISTRY  where images are tagged and pushed. Default: the registry
#                   `deploy.sh cluster` creates. Set it empty for bare
#                   `collabhub/<component>` names.
#   IMAGE_TAG       default: the short commit SHA, plus `-dirty` when the
#                   worktree has uncommitted changes. Never `latest`.
#   KUBE_CONTEXT    default: the k3d cluster's context. Nothing here falls back
#                   to kubectl's current context, which might be a real cluster.
#   DEPLOY_ENV      default: k3d. Selects charts/*/values-$DEPLOY_ENV.yaml.
#   NAMESPACE       default: collabhub. One instance per namespace.
#   APP_ORIGIN      the origin the browser uses, e.g. http://a.localhost:8080.
#                   Default: http://localhost:8080 on k3d; required elsewhere.
#
# Written for bash 3.2, which is what macOS ships: no associative arrays, and an
# empty array is expanded as ${arr[@]+"${arr[@]}"} because `set -u` rejects it
# otherwise.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

COMPONENTS=(auth messaging canvas asset worker frontend)

K3D_CLUSTER=collabhub
# k3d's only published port. Every instance on the cluster shares it, told apart
# by host: http://localhost:8080, http://a.localhost:8080, ...
K3D_ORIGIN=http://localhost:8080

# Which values files the charts install with: charts/*/values-$DEPLOY_ENV.yaml.
DEPLOY_ENV="${DEPLOY_ENV:-k3d}"
# One instance of CollabHub: its namespace, and the origin the browser reaches it
# on. The SPA, the APIs and Dex all sit behind that one origin, which is what
# register D22's SameSite=Strict cookie needs. deploy.sh resolves an empty
# APP_ORIGIN, because only k3d has a sensible default.
NAMESPACE="${NAMESPACE:-collabhub}"
APP_ORIGIN="${APP_ORIGIN:-}"

# The cluster add-on charts/collabhub's Worker pools scale with. Keep in step with
# the KEDA entry in docs/platform/versions.md.
KEDA_VERSION=2.20.2

# `-` not `:-` so an explicitly empty registry stays empty.
IMAGE_REGISTRY="${IMAGE_REGISTRY-localhost:5500}"
KUBE_CONTEXT="${KUBE_CONTEXT:-k3d-$K3D_CLUSTER}"

# Worked out once, when the script starts, so a build that runs for minutes
# cannot straddle an edit and tag half its images differently.
if [ -z "${IMAGE_TAG:-}" ]; then
    IMAGE_TAG="$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD)"
    if [ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]; then
        IMAGE_TAG="${IMAGE_TAG}-dirty"
    fi
fi

# Files charts/collabhub-deps reads from the repo rather than keeping a copy of.
# Helm cannot reach outside a chart's directory, so they arrive as --set-file.
DEPS_CHART_FILES=(
    --set-file "postgres.initSql=$REPO_ROOT/docker/postgres/init.sql"
    --set-file "garage.config=$REPO_ROOT/docker/garage/garage.toml"
    --set-file "otelCollector.config=$REPO_ROOT/docker/otel-collector/config.yaml"
)

if [ -t 2 ]; then
    _bold=$'\033[1m' _red=$'\033[31m' _reset=$'\033[0m'
else
    _bold='' _red='' _reset=''
fi

log() { printf '%s==> %s%s\n' "$_bold" "$*" "$_reset" >&2; }
die() {
    printf '%serror:%s %s\n' "$_red" "$_reset" "$*" >&2
    exit 1
}

# Prints the comment block at the top of the calling script, minus the `#`s.
usage() { sed -n '2,/^[^#]/s/^# \{0,1\}//p' "$0" | sed '$d'; }

require_cmd() {
    local cmd
    for cmd in "$@"; do
        command -v "$cmd" >/dev/null 2>&1 || die "'$cmd' is required and is not on PATH"
    done
}

is_component() {
    local c
    for c in "${COMPONENTS[@]}"; do
        [ "$c" = "$1" ] && return 0
    done
    return 1
}

image_ref() { printf '%scollabhub/%s:%s' "${IMAGE_REGISTRY:+$IMAGE_REGISTRY/}" "$1" "$IMAGE_TAG"; }

# The host part of an origin: http://a.localhost:8080 → a.localhost.
origin_host() {
    local host="${1#*://}"
    host="${host%%/*}"
    printf '%s' "${host%%:*}"
}
