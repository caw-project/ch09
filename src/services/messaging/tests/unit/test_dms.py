"""Direct messages — the pure rules (issue 5, plan decisions 7, 11, 12, 13).

A DM is a `kind='dm'` channel whose stored `name` is the pair key. These are the
decisions that need no database: the key itself, who the partner is, and which
channels may have their membership or name changed. Get-or-create, the listing
rule and concurrency need Postgres and are in `tests/integration/test_dms.py`.

The whole file needs `messaging.dms`, so a load failure is the right red.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from messaging import dms
from messaging.models import Channel

ADA = uuid.UUID("00000000-0000-4000-8000-00000000000a")
GRACE = uuid.UUID("ffffffff-ffff-4fff-8fff-fffffffffffe")
ALAN = uuid.UUID("77777777-7777-4777-8777-777777777777")
AT = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)


def _channel(name: str, kind: str) -> Channel:
    return Channel(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name=name,
        topic=None,
        kind=kind,
        created_by=ADA,
        created_at=AT,
        updated_at=AT,
        archived_at=None,
        version=0,
    )


def test_a_pair_has_one_name_whichever_way_round():
    """Breaks if the key depends on who opened the DM — two DMs for one pair."""
    assert dms.pair_name(ADA, GRACE) == dms.pair_name(GRACE, ADA)
    assert dms.pair_name(ADA, GRACE).startswith("dm:")


def test_pairs_sharing_one_person_have_different_names():
    """Breaks if the key is built from one id: it would pass the test above."""
    assert dms.pair_name(ADA, GRACE) != dms.pair_name(ADA, ALAN)
    assert dms.pair_name(ADA, GRACE) != dms.pair_name(GRACE, ALAN)


def test_a_dm_with_yourself_is_refused():
    """Breaks if `pair_name` accepts a pair of one — or refuses every pair."""
    with pytest.raises(dms.SelfDmError):
        dms.pair_name(ADA, ADA)

    assert dms.pair_name(ADA, GRACE)


def test_each_member_sees_the_other_as_partner():
    """Breaks if `partner_of` returns the caller, always the same side, or ignores the key."""
    dm = _channel(dms.pair_name(GRACE, ADA), "dm")

    assert dms.partner_of(dm, ADA) == GRACE
    assert dms.partner_of(dm, GRACE) == ADA
    assert dms.pair_of(dm) == (ADA, GRACE)  # (low, high), sorted


def test_only_a_dm_has_a_partner():
    """Kind decides, not the name: a private channel can't be made a DM by naming it."""
    imposter = _channel(dms.pair_name(ADA, GRACE), "private")

    assert dms.partner_of(imposter, ADA) is None
    assert dms.pair_of(imposter) is None
    # …and the same name on a real DM does give a partner, so None isn't the default.
    assert dms.partner_of(_channel(dms.pair_name(ADA, GRACE), "dm"), ADA) == GRACE


def test_a_dm_cannot_be_managed_and_a_channel_can():
    """Breaks if the guard refuses every kind, or lets a DM through."""
    with pytest.raises(dms.FixedChannelError):
        dms.check_manageable(_channel(dms.pair_name(ADA, GRACE), "dm"))

    dms.check_manageable(_channel("general", "public"))
    dms.check_manageable(_channel("leadership", "private"))
