"""Asset's internal API: what Messaging sends and what Asset answers (issue 4).

Both ends import these, so a renamed field breaks one build instead of drifting
between two. Asset's real routes answer with them and Messaging's client parses
them; Messaging's integration tests build a stub of Asset from the same models.

camelCase on the wire (Conventions §4), snake_case in Python.
`populate_by_name=True` lets a producer build a model by attribute name and
dump it `by_alias`.

**`workspace_id` travels in the body.** A service token carries no `wsp` claim,
so the workspace Messaging acts for is stated by Messaging, taken from the
caller's own token before the call (Conventions §5.5).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

#: One scope per internal route, as `assets:write-variants` does (register D14).
SCOPE_CLAIM = "assets:claim"
SCOPE_DOWNLOAD = "assets:download"

#: The most assets one claim may name. Messaging's own limit
#: (`MESSAGING_MAX_ATTACHMENTS`) is the rule; this is the wire's outer bound.
MAX_CLAIM_ASSETS = 10


class ClaimRefusal(StrEnum):
    """Why one asset cannot be claimed. The values are the wire's reason codes."""

    NOT_FOUND = "not-found"
    NOT_YOURS = "not-yours"
    NOT_READY = "not-ready"
    ALREADY_ATTACHED = "already-attached"


class _Wire(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ClaimRequest(_Wire):
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    message_id: uuid.UUID
    asset_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_CLAIM_ASSETS)


class AttachmentMeta(_Wire):
    """What a message keeps of an asset: enough to draw a chip, never a URL."""

    asset_id: uuid.UUID
    file_name: str
    content_type: str
    size_bytes: int


class ClaimResponse(_Wire):
    #: In the order of `ClaimRequest.asset_ids`.
    items: list[AttachmentMeta]


class DownloadUrlRequest(_Wire):
    workspace_id: uuid.UUID
    message_id: uuid.UUID


class DownloadUrlResponse(_Wire):
    url: str
    expires_at: datetime
