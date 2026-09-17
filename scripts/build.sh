#!/usr/bin/env bash
# Build CollabHub's container images. Developers and CI run this same script.
#
#   scripts/build.sh                  every component
#   scripts/build.sh auth messaging   only these
#   scripts/build.sh --push           build, then push to IMAGE_REGISTRY
#
# Images are tagged ${IMAGE_REGISTRY}/collabhub/<component>:${IMAGE_TAG}; the
# defaults are in scripts/lib/common.sh. The frontend's VITE_* URLs default to
# empty, so the SPA calls every API on its own origin and one image serves any
# environment behind a single ingress. Export them only to build for a stack
# that is not same-origin.
set -euo pipefail
# shellcheck source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

push=false
selected=()
while [ $# -gt 0 ]; do
    case "$1" in
        --push) push=true ;;
        -h | --help)
            usage
            exit 0
            ;;
        -*) die "unknown option '$1'" ;;
        *)
            is_component "$1" || die "unknown component '$1' (expected: ${COMPONENTS[*]})"
            selected+=("$1")
            ;;
    esac
    shift
done
[ ${#selected[@]} -gt 0 ] || selected=("${COMPONENTS[@]}")

require_cmd docker git

revision="$(git -C "$REPO_ROOT" rev-parse HEAD)"

for component in "${selected[@]}"; do
    ref="$(image_ref "$component")"
    args=(
        --file "$REPO_ROOT/docker/$component/Dockerfile"
        --tag "$ref"
        --label "org.opencontainers.image.revision=$revision"
    )
    if [ "$component" = frontend ]; then
        # Vite inlines these into the bundle. Empty means "same origin": every
        # call is relative to the page, so the image carries no environment and
        # the Ingress decides where it lives (register D40).
        args+=(
            --build-arg "VITE_AUTH_URL=${VITE_AUTH_URL-}"
            --build-arg "VITE_MESSAGING_URL=${VITE_MESSAGING_URL-}"
            --build-arg "VITE_CANVAS_URL=${VITE_CANVAS_URL-}"
            --build-arg "VITE_ASSET_URL=${VITE_ASSET_URL-}"
        )
    fi

    log "building $ref"
    # The context is the repo root: the uv lockfile is workspace-wide, so every
    # Python image needs the whole src/services tree to resolve.
    docker build "${args[@]}" "$REPO_ROOT"

    if $push; then
        log "pushing $ref"
        docker push "$ref"
    fi
done

log "built ${#selected[@]} image(s) at tag $IMAGE_TAG"
