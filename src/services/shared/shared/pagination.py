"""Cursor pagination, implemented once for every service (Conventions §4.1).

`?limit=` (default 50, max 200) and `?cursor=`; responses are `{items, nextCursor}`.
There is no `OFFSET` for a user-facing list, and that is the point of this module
rather than a stylistic preference. `OFFSET n` makes the database walk and
discard n rows, so page 500 costs five hundred times page 1; and because it
counts positions rather than naming a row, anything inserted or deleted while a
user pages shifts every later page under them — items get skipped or shown twice.

Keyset pagination asks "the rows after *this one*" instead. The cursor names the
sort key of the last row returned, the query seeks straight to it on an index,
and every page costs the same regardless of how deep it is.

The cursor is opaque on purpose. It is base64url of the sort-key parts, not
because that hides anything — it decodes trivially — but so that no client comes
to depend on its contents. What goes in it is whatever the query sorts by, and
that must be free to change without breaking callers holding an old cursor.

**The sort key must be unique.** A cursor on a non-unique column cannot say
which of the tied rows it meant, so ties straddling a page boundary get skipped
or repeated. Append the primary key to the sort — `(joined_at, user_id)`, not
`joined_at`.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query

from shared.problems import ProblemException

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

# Separates the parts of a composite sort key. A unit separator cannot appear in
# a UUID or a timestamp, so no part needs escaping.
_SEPARATOR = "\x1f"


def encode_cursor(*parts: str) -> str:
    """Pack sort-key parts into the opaque string a client sends back."""
    joined = _SEPARATOR.join(parts).encode()
    return base64.urlsafe_b64encode(joined).rstrip(b"=").decode()


CursorPart = Callable[[str], Any]
"""Turns one decoded cursor part into what the query needs — `uuid.UUID`,
`datetime.fromisoformat`, `str`. It refuses a part by raising `ValueError` or
`TypeError`."""


def _malformed() -> ProblemException:
    return ProblemException.validation_error(
        "The cursor is not valid.", errors={"cursor": ["Malformed cursor"]}
    )


def decode_cursor(cursor: str, *, parts: Sequence[CursorPart] | None = None) -> tuple[Any, ...]:
    """Unpack a cursor, or raise a 400 if it is not one we wrote.

    Base64 is only the envelope, so a cursor can decode cleanly and still be
    nothing this route wrote: another route's cursor, one part too many, a part
    that is not a UUID. Pass `parts` — one parser per sort-key part, in order —
    and those are the same 400 as bad base64, raised here, rather than a 500 from
    wherever the route unpacks the tuple. Without `parts` the raw strings come
    back unchecked.
    """
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = tuple(base64.urlsafe_b64decode(padded).decode().split(_SEPARATOR))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise _malformed() from None

    if parts is None:
        return raw
    if len(raw) != len(parts):
        raise _malformed()
    try:
        return tuple(parse(part) for parse, part in zip(parts, raw, strict=True))
    except (ValueError, TypeError):
        raise _malformed() from None


@dataclass(frozen=True)
class PageRequest:
    """A validated `?limit=`/`?cursor=` pair.

    `cursor` holds whatever the route's part parsers produced — typed values
    from `page_request_for`, raw strings from the untyped `page_request`.
    """

    limit: int
    cursor: tuple[Any, ...] | None

    @property
    def fetch_limit(self) -> int:
        """Ask the database for one more row than the caller wants.

        Whether a next page exists is then a fact about the rows in hand, rather
        than a second `COUNT(*)` over the whole table.
        """
        return self.limit + 1


def page_request(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query()] = None,
) -> PageRequest:
    """FastAPI dependency: `page: PageRequest = Depends(page_request)`.

    `limit` is bounded by FastAPI itself, so an out-of-range value is a 400 from
    the shared validation handler and never reaches a query.
    """
    return PageRequest(limit=limit, cursor=decode_cursor(cursor) if cursor else None)


PageParams = Annotated[PageRequest, Depends(page_request)]


def page_request_for(*parts: CursorPart) -> Callable[..., PageRequest]:
    """A page dependency for a route whose cursor holds exactly these parts.

    Prefer it to `PageParams` for any route that reads its cursor, which is
    all of them: `page: Annotated[PageRequest, Depends(page_request_for(uuid.UUID))]`.
    The route then gets typed parts, and a cursor of the wrong shape never
    reaches it.
    """

    def dependency(
        limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
        cursor: Annotated[str | None, Query()] = None,
    ) -> PageRequest:
        decoded = decode_cursor(cursor, parts=parts) if cursor else None
        return PageRequest(limit=limit, cursor=decoded)

    return dependency


@dataclass(frozen=True)
class Page[T]:
    """One page of rows, and the cursor that follows it."""

    items: list[T]
    next_cursor: str | None


def build_page[T](
    rows: Sequence[T], request: PageRequest, key: Callable[[T], tuple[str, ...]]
) -> Page[T]:
    """Trim an over-fetched result set into a page plus its next cursor.

    Pass the rows from a query that used `request.fetch_limit`. If the extra row
    came back there is another page; it is dropped here and the cursor is built
    from the last row actually returned.
    """
    has_more = len(rows) > request.limit
    items = list(rows[: request.limit])
    next_cursor = encode_cursor(*key(items[-1])) if has_more and items else None
    return Page(items=items, next_cursor=next_cursor)
