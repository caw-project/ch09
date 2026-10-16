#!/usr/bin/env bash
# Smoke-test a running CollabHub through its public origin, and nothing else.
#
#   scripts/smoke.sh                               this branch's preview
#   scripts/smoke.sh --origin http://localhost:8080   k3d, or any deploy
#   scripts/smoke.sh --out build/acceptance/feature build/acceptance/smoke
#                                                  another pack, run beside tests/smoke
#   scripts/smoke.sh -- -k sign_in                 anything after -- goes to pytest
#
# The packs are pytest + Playwright, with the fixtures in tests/smoke/fixtures.py
# loaded as a plugin, so a pack anywhere gets them. They are non-destructive: they
# reach the app only through the origin, and name anything they create with the
# run's id — safe against a preview someone is using.
#
#   --origin  default: APP_ORIGIN from `scripts/deploy.sh preview url`
#   --out     JUnit XML and screenshots/. Default: build/smoke. Never
#             docs/test-report.md, which is scripts/test.sh's.
#
# Exit status: pytest's.
set -euo pipefail
# shellcheck source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

origin=""
out=build/smoke
paths=()
pytest_args=()
while [ $# -gt 0 ]; do
    case "$1" in
        --origin)
            [ $# -ge 2 ] || die "--origin needs a URL"
            origin="$2"
            shift
            ;;
        --out)
            [ $# -ge 2 ] || die "--out needs a directory"
            out="$2"
            shift
            ;;
        --)
            shift
            pytest_args=("$@")
            break
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        -*) die "unknown option '$1'" ;;
        *)
            # Absolute now: pytest runs from the repo root, not from here.
            case "$1" in
                /*) paths+=("$1") ;;
                *) paths+=("$PWD/$1") ;;
            esac
            ;;
    esac
    shift
done

if [ -z "$origin" ]; then
    # A seam for the unit tests; nothing else sets it.
    preview="$("${SMOKE_DEPLOY_SH:-$REPO_ROOT/scripts/deploy.sh}" preview url)" ||
        die "no live preview for this branch — run scripts/deploy.sh preview up, or pass --origin"
    origin="$(printf '%s\n' "$preview" | sed -n 's/^APP_ORIGIN=//p')"
    [ -n "$origin" ] || die "scripts/deploy.sh preview url printed no APP_ORIGIN"
fi
origin="${origin%/}"
case "$origin" in
    http://?* | https://?*) ;;
    *) die "--origin must be an http:// or https:// URL, got '$origin'" ;;
esac

case "$out" in
    /*) ;;
    *) out="$REPO_ROOT/$out" ;;
esac
mkdir -p "$out"

log "smoke packs against $origin"
status=0
(cd "$REPO_ROOT" &&
    SMOKE_ORIGIN="$origin" SMOKE_OUT="$out" PYTHONPATH="$REPO_ROOT/tests${PYTHONPATH:+:$PYTHONPATH}" \
        uv run pytest -p smoke.fixtures tests/smoke ${paths[@]+"${paths[@]}"} \
        --junitxml="$out/junit.xml" ${pytest_args[@]+"${pytest_args[@]}"}) || status=$?
if [ "$status" = 0 ]; then
    log "smoke packs passed — $out/junit.xml, screenshots in $out/screenshots/"
else
    log "smoke packs failed (pytest exit $status) — $out/junit.xml, screenshots in $out/screenshots/"
fi
exit "$status"
