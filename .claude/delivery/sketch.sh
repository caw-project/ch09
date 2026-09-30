#!/usr/bin/env bash
# A throwaway copy of the SPA for the test-reviewer, so it can run the failing
# tests against a sketch of the plan's interfaces: a correct one, to prove each
# test can go green, and a wrong one, to prove the test catches it.
#
#   .claude/delivery/sketch.sh frontend          fresh copy, with the tests as they are now
#   .claude/delivery/sketch.sh test <paths>      Vitest in the copy; paths relative to src/frontend
#   .claude/delivery/sketch.sh diff              what the sketch changed against the worktree
#   .claude/delivery/sketch.sh clean             remove it — the code-writer builds from the plan, not from this
#
# The copy lives in build/sketch/, which git ignores and scripts/deliver.sh's
# write check skips, so a sketch never reaches the branch. Edit it with the
# Write and Edit tools under build/sketch/frontend/src/. `frontend` again
# starts over. node_modules is the worktree's own, linked, never copied.
#
# Run from the worktree root. Frontend only: a Python package imports its
# installed copy, not one under build/, so there is no Python sketch yet.
set -euo pipefail

SKETCH=build/sketch/frontend

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
    diff)
        diff -ru --exclude=node_modules src/frontend/src "$SKETCH/src" || true
        ;;
    clean)
        rm -rf build/sketch
        ;;
    *)
        sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
        exit 1
        ;;
esac
