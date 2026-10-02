#!/usr/bin/env bash
# A throwaway copy of the code, for the reviewers. The test-reviewer runs the
# failing tests against a sketch of the plan's interfaces: a correct one, to
# prove each test can go green, and a wrong one, to prove the test catches it.
# The code-reviewer does it the other way round: it breaks the writer's real
# code in the copy, to see which mistakes the green tests would catch.
#
#   .claude/delivery/sketch.sh frontend          fresh copy of the SPA, with the tests as they are now
#   .claude/delivery/sketch.sh test <paths>      Vitest in the copy; paths relative to src/frontend
#   .claude/delivery/sketch.sh service <name>…   fresh copy of src/services/<name>, tests included
#   .claude/delivery/sketch.sh pytest <args>     pytest against the copies; paths relative to src/services
#   .claude/delivery/sketch.sh reset <paths>     put files back as the worktree has them; paths as the
#                                                worktree names them (src/frontend/src/…, src/services/…)
#   .claude/delivery/sketch.sh diff              what the sketch changed against the worktree
#   .claude/delivery/sketch.sh clean             remove it — nothing built from this reaches the branch
#
# The copies live in build/sketch/, which git ignores and scripts/deliver.sh's
# write check skips, so a sketch never reaches the branch. Edit them with the
# Write and Edit tools under build/sketch/frontend/src/ and
# build/sketch/services/<name>/. `frontend` or `service <name>` again starts
# that copy over. node_modules is the worktree's own, linked, never copied.
#
# A Python package is installed from src/services, so the copies go first on
# PYTHONPATH: a copied service's tests import the copy, and everything not
# copied — `shared`, `testkit`, another service — is the worktree's own. Copy
# `shared` or `contracts` as well to change those. `pytest messaging/tests/unit`
# runs the copy's tests; integration tests start their containers as usual. The
# copy is outside src/services, so testkit sets no layer for it and a unit test
# there isn't cut off from the network — a sketch run proves behaviour, not the
# layer.
#
# Run from the worktree root.
set -euo pipefail

SKETCH=build/sketch/frontend
SERVICES=build/sketch/services

[ -d src/frontend ] || {
    echo "run this from the worktree root" >&2
    exit 1
}

case "${1:-}" in
    frontend)
        [ -d src/frontend/node_modules ] || {
            echo "no src/frontend/node_modules — run npm --prefix src/frontend ci first" >&2
            exit 1
        }
        rm -rf "$SKETCH"
        mkdir -p "$SKETCH"
        cp -R src/frontend/src src/frontend/openapi "$SKETCH/"
        cp src/frontend/package.json src/frontend/vite.config.ts src/frontend/tsconfig.json "$SKETCH/"
        ln -s "$PWD/src/frontend/node_modules" "$SKETCH/node_modules"
        echo "Sketch ready: edit $SKETCH/src/, then .claude/delivery/sketch.sh test <paths>"
        ;;
    test)
        shift
        [ -d "$SKETCH" ] || {
            echo "no sketch yet — run .claude/delivery/sketch.sh frontend" >&2
            exit 1
        }
        cd "$SKETCH" && exec node_modules/.bin/vitest run "$@"
        ;;
    service)
        shift
        [ $# -gt 0 ] || {
            echo "name a service: .claude/delivery/sketch.sh service messaging" >&2
            exit 1
        }
        for name in "$@"; do
            [ -d "src/services/$name" ] || {
                echo "no src/services/$name" >&2
                exit 1
            }
            rm -rf "$SERVICES/$name"
            mkdir -p "$SERVICES"
            cp -R "src/services/$name" "$SERVICES/$name"
            find "$SERVICES/$name" -name __pycache__ -type d -prune -exec rm -rf {} +
        done
        echo "Sketch ready: edit $SERVICES/<name>/, then .claude/delivery/sketch.sh pytest <name>/tests/unit/<file>"
        ;;
    pytest)
        shift
        [ -d "$SERVICES" ] || {
            echo "no service copied yet — run .claude/delivery/sketch.sh service <name>" >&2
            exit 1
        }
        path=""
        for dir in "$SERVICES"/*/; do path="$PWD/${dir%/}${path:+:$path}"; done
        args=()
        for arg in "$@"; do
            if [ -e "$SERVICES/${arg%%::*}" ]; then args+=("$SERVICES/$arg"); else args+=("$arg"); fi
        done
        PYTHONPATH="$path" exec uv run pytest -p no:cacheprovider ${args[@]+"${args[@]}"}
        ;;
    reset)
        shift
        for file in "$@"; do
            case "$file" in
                src/frontend/*) target="$SKETCH/${file#src/frontend/}" ;;
                src/services/*) target="$SERVICES/${file#src/services/}" ;;
                *)
                    echo "not a path the sketch copies: $file" >&2
                    exit 1
                    ;;
            esac
            if [ -f "$file" ]; then cp "$file" "$target"; else rm -f "$target"; fi
        done
        ;;
    diff)
        [ ! -d "$SKETCH" ] || diff -ru --exclude=node_modules src/frontend/src "$SKETCH/src" || true
        if [ -d "$SERVICES" ]; then
            for dir in "$SERVICES"/*/; do
                name="$(basename "$dir")"
                diff -ru --exclude=__pycache__ "src/services/$name" "$SERVICES/$name" || true
            done
        fi
        ;;
    clean)
        rm -rf build/sketch
        ;;
    *)
        sed -n '2,31p' "$0" | sed 's/^# \{0,1\}//'
        exit 1
        ;;
esac
