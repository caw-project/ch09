"""The images integration tests start — the same tags `docker-compose.yml` runs.

`docs/platform/versions.md` is the source of truth for these, and
`tests/unit/test_images.py` fails when this file and Compose disagree.

Garage's pin is here because `testkit.garage` starts it for the tests that sign
and fetch real objects (register D34).
"""

from __future__ import annotations

POSTGRES = "postgres:18"
REDIS = "redis:8"
ELASTICSEARCH = "docker.elastic.co/elasticsearch/elasticsearch:9.4.3"
DEX = "ghcr.io/dexidp/dex:v2.45.1"
GARAGE = "dxflrs/garage:v2.3.0"
