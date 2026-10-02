"""The Garage fixture, and what the bootstrap leaves behind (register D34, issue 4 R16).

The fixture runs the real `garage-bootstrap.py`, so these tests are also the
bootstrap's: the bucket exists and the key may use it, the S3 API is up, and the
bucket's CORS lets the app's origin PUT to it and nobody else's.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def _admin(garage, path: str) -> dict:
    request = urllib.request.Request(  # noqa: S310 - a container on localhost
        f"{garage.admin_url}/v2/{path}",
        headers={"Authorization": f"Bearer {garage.admin_token}"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        return json.loads(response.read())


def _request(
    url: str, *, method: str, headers: dict[str, str]
) -> tuple[int, dict[str, str], bytes]:
    """Status, lower-cased headers and body — a 4xx is an answer here, not an exception."""
    request = urllib.request.Request(url, method=method, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return (
                response.status,
                {k.lower(): v for k, v in response.headers.items()},
                response.read(),
            )
    except urllib.error.HTTPError as error:
        return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read()


def test_the_bootstrap_makes_the_bucket_and_allows_the_key(garage_server):
    info = _admin(garage_server, f"GetBucketInfo?globalAlias={garage_server.bucket}")

    keys = {key["accessKeyId"]: key["permissions"] for key in info["keys"]}
    assert keys[garage_server.access_key]["read"] is True
    assert keys[garage_server.access_key]["write"] is True

    status, _, body = _request(
        f"{garage_server.endpoint}/{garage_server.bucket}/", method="GET", headers={}
    )
    assert 400 <= status < 500
    assert b"<Error>" in body


def test_cors_preflight_allows_only_the_app_origin(garage_server):
    """Both halves in one test: the allowed origin is answered, the other is not.

    A bucket with no CORS rules fails the first assertion; a bucket that allows
    every origin fails the last. Garage answers a refused preflight with a 403
    that still carries `access-control-allow-origin: *`, so the refusal is the
    status — a browser needs a 2xx preflight — and the header never names the
    refused origin.
    """
    url = f"{garage_server.endpoint}/{garage_server.bucket}/some-key"

    def preflight(origin: str) -> tuple[int, dict[str, str]]:
        status, headers, _ = _request(
            url,
            method="OPTIONS",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        return status, headers

    allowed_status, allowed = preflight(garage_server.cors_origin)
    assert allowed_status < 300
    assert allowed.get("access-control-allow-origin") == garage_server.cors_origin

    refused_status, refused = preflight("http://evil.test")
    assert not 200 <= refused_status < 300
    assert refused.get("access-control-allow-origin") != "http://evil.test"
