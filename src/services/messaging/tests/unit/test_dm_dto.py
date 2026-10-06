"""The wire shape of `dmPartnerId` on `ChannelResponse` (issue 5, decision 10)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from messaging.channels import VisibleChannel
from messaging.models import Channel
from messaging.routers.channels import _as_channel

ADA = uuid.uuid4()
GRACE = uuid.uuid4()
WORKSPACE = uuid.uuid4()
AT = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)


def _channel(kind: str, name: str) -> Channel:
    return Channel(
        id=uuid.uuid4(),
        workspace_id=WORKSPACE,
        name=name,
        topic=None,
        kind=kind,
        created_by=ADA,
        created_at=AT,
        updated_at=AT,
        archived_at=None,
        version=0,
    )


def test_the_dto_carries_the_partner():
    """Breaks if `_as_channel` drops the partner or reads it from the wrong attribute."""
    visible = VisibleChannel(
        channel=_channel("dm", f"dm:{ADA}:{GRACE}"),
        my_role="member",
        last_read_id=None,
        unread_count=0,
        dm_partner_id=GRACE,
    )

    body = _as_channel(visible).model_dump(mode="json", by_alias=True)

    assert body["dmPartnerId"] == str(GRACE)


def test_a_channel_dto_has_a_null_partner_key():
    """Required, not omitted — so the generated TypeScript is `string | null`, not optional."""
    visible = VisibleChannel(
        channel=_channel("public", "general"),
        my_role="member",
        last_read_id=None,
        unread_count=0,
    )

    body = _as_channel(visible).model_dump(mode="json", by_alias=True)

    assert "dmPartnerId" in body
    assert body["dmPartnerId"] is None
