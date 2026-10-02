"""SQLAlchemy models for the Asset service's own database (design doc 04 §4).

`workspace_id`, `owner_id` and `message_id` name rows in other services'
databases, so none carries a foreign key (Conventions §2).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Every timestamp on the platform is UTC `timestamptz` (Conventions §3).
Timestamp = TIMESTAMP(timezone=True)

PENDING = "pending"
READY = "ready"
FAILED = "failed"


class Base(DeclarativeBase):
    pass


class Asset(Base):
    """One uploaded file: its metadata, and where its bytes are.

    **`message_id` is the claim.** It is set once, by Messaging's claim call,
    and a download is only ever minted for the message that holds it. The
    uniqueness that matters — one asset on one message — is enforced by the
    claim locking the row, not by a constraint, because the message lives in
    another database.
    """

    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("bucket", "object_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    bucket: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=PENDING)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
