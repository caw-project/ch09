"""Signing-key sources for token verification (Conventions §5.1).

Every service verifies RS256 tokens locally against the Auth service's JWKS —
there is no per-request call to Auth — so the behaviour that matters here is
caching: fetch once, refresh when an unknown `kid` shows up, and re-fetch
hourly. Auth itself holds the private key and uses `StaticKeySource` instead of
HTTP-calling its own endpoint.
"""

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from shared import (
    JwksClient,
    KeySourceUnavailableError,
    StaticKeySource,
    UnknownKeyError,
    jwks_document,
    keys,
)
from shared.keys import DEFAULT_HARD_REFRESH_SECONDS, DEFAULT_MIN_REFRESH_SECONDS


@pytest.fixture(scope="module")
def key_pair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def other_key_pair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _JwksServer:
    """A stand-in Auth service that counts how often its JWKS is fetched."""

    def __init__(self, document: dict) -> None:
        self.document = document
        self.fetches = 0
        self.app = Starlette(routes=[Route("/.well-known/jwks.json", self._serve)])

    async def _serve(self, request: httpx.Request) -> JSONResponse:
        self.fetches += 1
        return JSONResponse(self.document)

    def client(self, **kwargs) -> JwksClient:
        transport = httpx.ASGITransport(app=self.app)
        http = httpx.AsyncClient(transport=transport, base_url="http://auth")
        return JwksClient("http://auth/.well-known/jwks.json", http_client=http, **kwargs)


def test_jwks_document_publishes_only_public_material(key_pair: rsa.RSAPrivateKey) -> None:
    document = jwks_document({"key-1": key_pair.public_key()})

    assert len(document["keys"]) == 1
    key = document["keys"][0]
    assert key["kid"] == "key-1"
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert key["use"] == "sig"
    # The private exponent and primes must never appear in a published document.
    assert not {"d", "p", "q", "dp", "dq", "qi"} & set(key)


async def test_static_source_returns_the_key_for_a_known_id(key_pair: rsa.RSAPrivateKey) -> None:
    source = StaticKeySource({"key-1": key_pair.public_key()})

    assert await source.key_for("key-1") is not None


async def test_static_source_rejects_an_unknown_key_id(key_pair: rsa.RSAPrivateKey) -> None:
    source = StaticKeySource({"key-1": key_pair.public_key()})

    with pytest.raises(UnknownKeyError):
        await source.key_for("key-2")


async def test_jwks_client_fetches_once_and_caches(key_pair: rsa.RSAPrivateKey) -> None:
    server = _JwksServer(jwks_document({"key-1": key_pair.public_key()}))
    client = server.client()

    await client.key_for("key-1")
    await client.key_for("key-1")

    assert server.fetches == 1


async def test_jwks_client_refetches_when_it_sees_an_unknown_key_id(
    key_pair: rsa.RSAPrivateKey, other_key_pair: rsa.RSAPrivateKey
) -> None:
    """Key rotation: Auth starts signing with a new kid and services follow."""
    server = _JwksServer(jwks_document({"key-1": key_pair.public_key()}))
    client = server.client(min_refresh_seconds=0)
    await client.key_for("key-1")

    server.document = jwks_document(
        {"key-1": key_pair.public_key(), "key-2": other_key_pair.public_key()}
    )

    assert await client.key_for("key-2") is not None
    assert server.fetches == 2


async def test_jwks_client_still_rejects_an_id_the_refetch_did_not_produce(
    key_pair: rsa.RSAPrivateKey,
) -> None:
    server = _JwksServer(jwks_document({"key-1": key_pair.public_key()}))
    client = server.client(min_refresh_seconds=0)

    with pytest.raises(UnknownKeyError):
        await client.key_for("nonsense")


async def test_jwks_client_does_not_refetch_faster_than_its_floor(
    key_pair: rsa.RSAPrivateKey,
) -> None:
    """A burst of tokens with a bogus kid must not become a burst of fetches."""
    server = _JwksServer(jwks_document({"key-1": key_pair.public_key()}))
    client = server.client(min_refresh_seconds=300)
    await client.key_for("key-1")

    for _ in range(5):
        with pytest.raises(UnknownKeyError):
            await client.key_for("bogus")

    assert server.fetches == 2


# --- Auth is down -----------------------------------------------------------
#
# Stateless verification exists so that Auth is not on the critical path of
# every request (Conventions §5.1). The hourly refresh must not put it back
# there: a refresh that fails while valid keys are cached keeps serving them, and
# a fetch that fails with no usable key is `KeySourceUnavailableError` — an
# `UnknownKeyError`, so no caller is left with nothing to catch, but one that
# verification turns into a 503 rather than a 401. Never a raw `httpx`
# exception, which reaches the client as a 500.

JWKS_URL = "http://auth/.well-known/jwks.json"
OUTAGES = pytest.mark.parametrize("outage", ["unreachable", "erroring"])


class _Clock:
    """Stands in for the `time` module inside `shared.keys`, so an hour passes at once."""

    def __init__(self) -> None:
        self.now = 10_000.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    # The name inside `shared.keys` only. Patching `time.monotonic` itself would
    # stop the event loop's own clock too.
    monkeypatch.setattr(keys, "time", fake)
    return fake


class _FlakyAuth:
    """A stand-in Auth whose JWKS endpoint can be taken down."""

    def __init__(self, document: dict) -> None:
        self.document = document
        self.state = "up"
        self.requests = 0

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        if self.state == "unreachable":
            raise httpx.ConnectError("connection refused", request=request)
        if self.state == "erroring":
            return httpx.Response(503)
        return httpx.Response(200, json=self.document)

    def client(self, **kwargs) -> JwksClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(self._handle))
        return JwksClient(JWKS_URL, http_client=http, **kwargs)


@OUTAGES
async def test_jwks_client_keeps_serving_cached_keys_when_the_hourly_refresh_fails(
    key_pair: rsa.RSAPrivateKey, clock: _Clock, outage: str
) -> None:
    auth = _FlakyAuth(jwks_document({"key-1": key_pair.public_key()}))
    client = auth.client()
    cached = await client.key_for("key-1")

    clock.advance(DEFAULT_HARD_REFRESH_SECONDS + 1)
    auth.state = outage

    assert await client.key_for("key-1") is cached
    assert auth.requests == 2, "the scheduled refresh should still have been attempted"


@OUTAGES
async def test_jwks_client_retries_a_failed_hourly_refresh_on_a_later_call(
    key_pair: rsa.RSAPrivateKey, clock: _Clock, outage: str
) -> None:
    """A failure must not count as a refresh, or the next one is an hour away."""
    auth = _FlakyAuth(jwks_document({"key-1": key_pair.public_key()}))
    client = auth.client()
    await client.key_for("key-1")
    clock.advance(DEFAULT_HARD_REFRESH_SECONDS + 1)
    auth.state = outage
    await client.key_for("key-1")

    auth.state = "up"
    clock.advance(DEFAULT_MIN_REFRESH_SECONDS + 1)

    assert await client.key_for("key-1") is not None
    assert auth.requests == 3


@OUTAGES
async def test_jwks_client_reports_an_unknown_key_when_the_first_fetch_fails(
    clock: _Clock, outage: str
) -> None:
    """Auth down while a service starts: no key is held, so no token can be verified."""
    auth = _FlakyAuth({"keys": []})
    auth.state = outage
    client = auth.client()

    with pytest.raises(KeySourceUnavailableError):
        await client.key_for("key-1")


@OUTAGES
async def test_jwks_client_reports_an_unknown_key_when_a_kid_miss_fetch_fails(
    key_pair: rsa.RSAPrivateKey, clock: _Clock, outage: str
) -> None:
    auth = _FlakyAuth(jwks_document({"key-1": key_pair.public_key()}))
    client = auth.client()
    await client.key_for("key-1")
    auth.state = outage

    with pytest.raises(KeySourceUnavailableError):
        await client.key_for("key-2")

    # The key it already holds is unaffected.
    assert await client.key_for("key-1") is not None
