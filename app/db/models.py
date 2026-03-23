"""
Kesiyos Bot — Database Models

SQLAlchemy ORM models for the kesiyos_bot database.
All tables use UUID primary keys and UTC timestamps.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Platform(str, enum.Enum):
    MESSENGER = "messenger"
    INSTAGRAM = "instagram"


class ConversationStatus(str, enum.Enum):
    ACTIVE = "active"
    ESCALATED = "escalated"
    RESOLVED = "resolved"


class MessageDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class SenderType(str, enum.Enum):
    CUSTOMER = "customer"
    BOT = "bot"
    HUMAN = "human"


class EscalationTier(int, enum.Enum):
    TIER_2 = 2
    TIER_3 = 3


class SyncType(str, enum.Enum):
    SALE_ORDER = "sale_order"
    RESERVATION = "reservation"
    NEW_CONTACT = "new_contact"


class SyncStatus(str, enum.Enum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Conversation(Base):
    """
    Tracks a conversation thread with a single customer.
    One customer can have multiple conversations over time.
    """
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, native_enum=True), nullable=False
    )
    platform_sender_id: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="PSID (Messenger) or IGSID (Instagram)"
    )
    customer_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="From profile API if available"
    )
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, native_enum=True),
        nullable=False,
        default=ConversationStatus.ACTIVE,
    )
    current_tier: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
        comment="Current classification tier: 1=auto, 2=gathering, 3=escalate"
    )
    intent_category: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Latest intent: menu, hours, order, reservation, complaint, etc."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    # Relationships
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.created_at"
    )
    escalations: Mapped[list["Escalation"]] = relationship(
        back_populates="conversation"
    )
    sync_queue_items: Mapped[list["OdooSyncQueue"]] = relationship(
        back_populates="conversation"
    )

    __table_args__ = (
        Index("ix_conversations_platform_sender", "platform", "platform_sender_id"),
        Index("ix_conversations_status", "status"),
        Index("ix_conversations_updated_at", "updated_at"),
    )


class Message(Base):
    """
    Individual message within a conversation.
    Stores both inbound (customer) and outbound (bot/human) messages.
    """
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection, native_enum=True), nullable=False
    )
    sender_type: Mapped[SenderType] = mapped_column(
        Enum(SenderType, native_enum=True), nullable=False
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    claude_classification: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Claude response: {tier, category, confidence, reasoning}"
    )
    platform_message_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True,
        comment="Meta message ID for deduplication"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_created_at", "created_at"),
        UniqueConstraint("platform_message_id", name="uq_messages_platform_id"),
    )


class Escalation(Base):
    """
    Records when a conversation is escalated to human staff.
    Tracks the full lifecycle: escalated → notified → resolved.
    """
    __tablename__ = "escalations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    tier: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="2 = info gathered, 3 = immediate escalation"
    )
    reason: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Why the bot escalated this conversation"
    )
    collected_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Structured data gathered by bot: order details, reservation info, etc."
    )
    staff_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    staff_resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Staff member who handled it"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="escalations")

    __table_args__ = (
        Index("ix_escalations_conversation_id", "conversation_id"),
        Index("ix_escalations_unresolved", "staff_resolved_at",
              postgresql_where="staff_resolved_at IS NULL"),
    )


class OdooSyncQueue(Base):
    """
    Queue for data that needs to be pushed to Odoo.
    The Odoo connector (Phase 2) reads from here and syncs via XML-RPC.
    """
    __tablename__ = "odoo_sync_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    sync_type: Mapped[SyncType] = mapped_column(
        Enum(SyncType, native_enum=True), nullable=False
    )
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        comment="Structured data ready for Odoo: items, quantities, customer info, etc."
    )
    status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, native_enum=True), nullable=False, default=SyncStatus.PENDING
    )
    synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    # Relationships
    conversation: Mapped["Conversation | None"] = relationship(
        back_populates="sync_queue_items"
    )

    __table_args__ = (
        Index("ix_sync_queue_pending", "status",
              postgresql_where="status = 'pending'"),
        Index("ix_sync_queue_created_at", "created_at"),
    )
