#!/bin/sh
# Migrate, then run whatever the image's CMD is.
#
# Convenient locally, where one container is the whole deployment. In Kubernetes
# set RUN_MIGRATIONS=false and run `python -m asset.migrate` as a pre-upgrade
# Job instead — several replicas rolling out at once should not each try to
# migrate.
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "asset: applying database migrations"
    python -m asset.migrate
fi

exec "$@"
