"""Cursor pagination (Conventions §4.1).

The behaviour worth pinning down is the boundary: a cursor is built from the
last row *returned*, not the last row fetched, and the over-fetched extra row is
what tells us another page exists. Off by one here either drops a row between
pages or repeats one.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from shared import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    PageRequest,
    build_page,
    decode_cursor,
    encode_cursor,
    page_request_for,
)
from shared.problems import ProblemException


@dataclass(frozen=True)
class Row:
    at: str
    id: str


def rows(n: int) -> list[Row]:
    return [Row(at=f"2026-07-28T10:0{i}:00+00:00", id=f"id-{i}") for i in range(n)]


def key(row: Row) -> tuple[str, ...]:
    return (row.at, row.id)


def request(limit: int = 2, cursor: str | None = None) -> PageRequest:
    return PageRequest(limit=limit, cursor=decode_cursor(cursor) if cursor else None)


# --- the cursor itself -----------------------------------------------------


def test_a_cursor_round_trips() -> None:
    assert decode_cursor(encode_cursor("2026-07-28T10:00:00+00:00", "abc")) == (
        "2026-07-28T10:00:00+00:00",
        "abc",
    )


def test_a_cursor_is_opaque() -> None:
    """Not secret — just not something a client should learn to parse."""
    cursor = encode_cursor("2026-07-28T10:00:00+00:00", "abc")

    assert ":" not in cursor
    assert "=" not in cursor  # padding stripped, so it is URL-safe bare


def test_a_single_part_cursor_round_trips() -> None:
    assert decode_cursor(encode_cursor("only")) == ("only",)


def test_a_malformed_cursor_is_a_validation_error() -> None:
    with pytest.raises(ProblemException) as raised:
        decode_cursor("!!!not base64!!!")

    assert raised.value.status == 400
    assert "cursor" in (raised.value.errors or {})


# --- the parts a route expects ---------------------------------------------
#
# Base64 is only the envelope. A cursor that decodes cleanly can still hold the
# wrong number of parts, or a part the query cannot use, and that is the same
# client mistake as bad base64 — never a 500 from wherever the part is unpacked.

AT = "2026-07-28T10:00:00+00:00"
ID = "0198f1a2-7b3c-7d4e-8f50-6a7b8c9d0e1f"


def _refusal(cursor: str, *parts: Callable[[str], object]) -> ProblemException:
    with pytest.raises(ProblemException) as raised:
        decode_cursor(cursor, parts=parts)
    return raised.value


def test_a_cursor_decodes_into_the_types_its_parts_name() -> None:
    at, id_ = decode_cursor(encode_cursor(AT, ID), parts=(datetime.fromisoformat, uuid.UUID))

    assert at == datetime(2026, 7, 28, 10, 0, tzinfo=UTC)
    assert id_ == uuid.UUID(ID)


@pytest.mark.parametrize(
    "cursor",
    [
        pytest.param(encode_cursor(ID, "extra"), id="too-many"),
        pytest.param(encode_cursor(AT), id="too-few"),
    ],
)
def test_a_cursor_with_the_wrong_number_of_parts_is_a_validation_error(cursor: str) -> None:
    problem = _refusal(cursor, datetime.fromisoformat, uuid.UUID)

    assert problem.status == 400
    assert problem.errors == {"cursor": ["Malformed cursor"]}


@pytest.mark.parametrize(
    ("cursor", "parts"),
    [
        pytest.param(encode_cursor("not-a-uuid"), (uuid.UUID,), id="uuid"),
        pytest.param(encode_cursor("yesterday", ID), (datetime.fromisoformat, uuid.UUID), id="ts"),
    ],
)
def test_a_part_its_parser_refuses_is_a_validation_error(
    cursor: str, parts: tuple[Callable[[str], object], ...]
) -> None:
    problem = _refusal(cursor, *parts)

    assert problem.status == 400
    assert problem.errors == {"cursor": ["Malformed cursor"]}


def test_the_page_dependency_for_a_route_returns_typed_parts() -> None:
    page = page_request_for(uuid.UUID)(limit=10, cursor=encode_cursor(ID))

    assert page.limit == 10
    assert page.cursor == (uuid.UUID(ID),)


def test_the_page_dependency_for_a_route_refuses_a_cursor_of_the_wrong_shape() -> None:
    with pytest.raises(ProblemException) as raised:
        page_request_for(uuid.UUID)(limit=10, cursor=encode_cursor("general", ID))

    assert raised.value.status == 400
    assert raised.value.errors == {"cursor": ["Malformed cursor"]}


def test_the_page_dependency_for_a_route_allows_no_cursor() -> None:
    assert page_request_for(uuid.UUID)(limit=10, cursor=None).cursor is None


# --- paging ----------------------------------------------------------------


def test_a_short_result_set_has_no_next_cursor() -> None:
    page = build_page(rows(2), request(limit=2), key=key)

    assert len(page.items) == 2
    assert page.next_cursor is None


def test_an_over_fetched_row_signals_another_page() -> None:
    """The query asks for `fetch_limit`; the extra row is dropped here."""
    page = build_page(rows(3), request(limit=2), key=key)

    assert len(page.items) == 2
    assert page.next_cursor is not None


def test_the_cursor_names_the_last_row_returned_not_the_one_dropped() -> None:
    """The off-by-one that repeats or skips a row.

    The over-fetched third row is the *first row of the next page*, so the
    cursor has to point at the second — the last one the caller actually saw.
    """
    page = build_page(rows(3), request(limit=2), key=key)

    assert decode_cursor(page.next_cursor) == key(rows(3)[1])


def test_an_empty_result_set_has_no_cursor() -> None:
    page = build_page([], request(limit=2), key=key)

    assert page.items == []
    assert page.next_cursor is None


def test_exactly_one_page_has_no_cursor() -> None:
    """A result set the same size as the limit is the last page, not a full one."""
    page = build_page(rows(2), request(limit=2), key=key)

    assert page.next_cursor is None


def test_fetch_limit_is_one_more_than_asked_for() -> None:
    assert request(limit=50).fetch_limit == 51


def test_the_conventional_limits_are_what_the_conventions_say() -> None:
    assert DEFAULT_LIMIT == 50
    assert MAX_LIMIT == 200
