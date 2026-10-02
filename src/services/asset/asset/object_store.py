"""The `ObjectStore` protocol, and the S3-compatible store behind it.

Everything else in Asset talks to `ObjectStore`, never to boto3, so Garage ↔
Azure Blob is a configuration swap and no route learns what signs its URLs. The
only S3 vocabulary that leaks is the three operations a browser-direct design
needs: a URL to PUT to, a URL to GET from, and the size of what arrived.

**Two clients, on purpose.** A presigned URL's host is part of its signature, so
URLs have to be signed for the endpoint a *browser* can reach
(`OBJECT_STORE_PUBLIC_ENDPOINT`, e.g. `localhost:3900`) — while the service's own
HEAD goes to the endpoint it can reach (`OBJECT_STORE_ENDPOINT`, e.g.
`garage:3900`). Signing never touches the network, so the public client is never
dialled.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Protocol

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

#: Garage ignores the region but SigV4 needs one, and it has to be the same
#: string on both ends of a signature.
_REGION = "garage"

#: Answers that mean "there is no such object" rather than "the store is sick".
_MISSING = {"404", "NoSuchKey", "NotFound"}


class ObjectStoreUnavailableError(Exception):
    """The store could not be reached, or refused the service's own credentials."""


class ObjectStore(Protocol):
    def presign_put(self, key: str, content_type: str) -> tuple[str, datetime]:
        """A URL a browser can PUT the object to. The `Content-Type` is part of the signature."""
        ...

    def presign_get(self, key: str, content_disposition: str) -> tuple[str, datetime]:
        """A URL a browser can GET the object from, with the disposition it must be served with."""
        ...

    async def head(self, key: str) -> int | None:
        """The stored size in bytes, or `None` when there is no such object."""
        ...


class S3ObjectStore:
    def __init__(
        self,
        *,
        endpoint: str,
        public_endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        presign_ttl_seconds: int,
    ) -> None:
        self._bucket = bucket
        self._ttl = presign_ttl_seconds
        self._public = self._client(public_endpoint, access_key, secret_key)
        self._internal = self._client(endpoint, access_key, secret_key)

    @staticmethod
    def _client(endpoint: str, access_key: str, secret_key: str) -> BaseClient:
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=_REGION,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                # A send waits on these: fail fast rather than retry into a timeout.
                connect_timeout=3,
                read_timeout=5,
                retries={"max_attempts": 1, "mode": "standard"},
            ),
        )

    def _expires_at(self) -> datetime:
        return datetime.now(UTC) + timedelta(seconds=self._ttl)

    def presign_put(self, key: str, content_type: str) -> tuple[str, datetime]:
        url = self._public.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=self._ttl,
        )
        return url, self._expires_at()

    def presign_get(self, key: str, content_disposition: str) -> tuple[str, datetime]:
        url = self._public.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ResponseContentDisposition": content_disposition,
            },
            ExpiresIn=self._ttl,
        )
        return url, self._expires_at()

    def _head(self, key: str) -> int | None:
        try:
            result = self._internal.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if str(exc.response.get("Error", {}).get("Code")) in _MISSING:
                return None
            raise ObjectStoreUnavailableError from exc
        except BotoCoreError as exc:
            raise ObjectStoreUnavailableError from exc
        return int(result["ContentLength"])

    async def head(self, key: str) -> int | None:
        # boto3 is synchronous: on a thread, so a slow store does not stall the loop.
        return await asyncio.to_thread(self._head, key)
