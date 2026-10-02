"""`S3ObjectStore` against a real Garage — what boto3's signing and Garage's checks agree on.

No part of this can be a unit test: whether Garage accepts a signed URL, enforces
the signed `Content-Type`, answers HEAD and honours
`response-content-disposition` is a fact about Garage. Nothing is stubbed.

`S3ObjectStore(endpoint=, public_endpoint=, access_key=, secret_key=, bucket=,
presign_ttl_seconds=)` is the constructor these tests assume; the plan fixes the
protocol (`presign_put`, `presign_get`, `head`) and leaves the arguments open.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
import pytest

from testkit.garage import GarageServer

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture
def store(garage_server: GarageServer):

    return build(garage_server, public_endpoint=garage_server.endpoint)


def build(garage: GarageServer, *, public_endpoint: str):
    from asset.object_store import S3ObjectStore

    return S3ObjectStore(
        endpoint=garage.endpoint,
        public_endpoint=public_endpoint,
        access_key=garage.access_key,
        secret_key=garage.secret_key,
        bucket=garage.bucket,
        presign_ttl_seconds=900,
    )


async def put(store, key: str, content: bytes, content_type: str) -> httpx.Response:
    url, _ = store.presign_put(key, content_type)
    async with httpx.AsyncClient() as http:
        return await http.put(url, content=content, headers={"Content-Type": content_type})


async def test_presigned_put_stores_the_bytes(store, an_object_key):
    """Breaks if the URL is not one Garage will accept a PUT on, or HEAD cannot see the result."""
    key = an_object_key()

    response = await put(store, key, PDF, "application/pdf")

    assert response.status_code == 200, response.text
    assert await store.head(key) == len(PDF)


async def test_presigned_put_signs_the_content_type(store, an_object_key):
    """The allow-list rests on this: a URL for image/png must not take text/plain.

    The positive half is the PUT with the signed type in the test above; this
    one asserts the object is not there afterwards, so a 403 that still stored
    the bytes would fail too.
    """
    key = an_object_key()
    url, _ = store.presign_put(key, "image/png")

    async with httpx.AsyncClient() as http:
        refused = await http.put(url, content=b"<script>", headers={"Content-Type": "text/plain"})
        accepted = await http.put(url, content=b"\x89PNG", headers={"Content-Type": "image/png"})

    assert refused.status_code == 403
    assert accepted.status_code == 200
    assert await store.head(key) == 4


async def test_head_reports_the_size(store, an_object_key):
    key = an_object_key()
    await put(store, key, b"x" * 1234, "image/png")

    assert await store.head(key) == 1234


async def test_head_of_a_missing_key_is_none(store, an_object_key):
    """Confirm turns a missing object into `failed`: breaks if a 404 raises instead."""
    assert await store.head(an_object_key()) is None


async def test_presigned_get_carries_the_disposition(store, an_object_key):
    """Breaks if Garage ignores the signed override, or the store does not sign it."""
    key = an_object_key()
    await put(store, key, PDF, "application/pdf")
    disposition = "attachment; filename*=UTF-8''notes.pdf"

    url, expires_at = store.presign_get(key, disposition)
    async with httpx.AsyncClient() as http:
        response = await http.get(url)

    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-disposition"] == disposition
    assert expires_at > datetime.now(UTC)


async def test_urls_are_signed_for_the_public_endpoint(garage_server, an_object_key):
    """R16: a URL for `garage:3900` is useless to a browser, and the host is part of the signature."""
    public = "http://s3.public.test:3900"
    store = build(garage_server, public_endpoint=public)
    key = an_object_key()

    put_url, _ = store.presign_put(key, "image/png")
    get_url, _ = store.presign_get(key, "inline")

    assert urlsplit(put_url).netloc == "s3.public.test:3900"
    assert urlsplit(get_url).netloc == "s3.public.test:3900"
    # The positive: the *internal* client still reaches the store, so HEAD works
    # even though no URL it signs would be fetched from here.
    assert await store.head(key) is None
