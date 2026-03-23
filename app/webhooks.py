"""
Kesiyos Bot — Meta Webhook Receiver
Handles incoming messages from Facebook Messenger and Instagram DMs.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_session
from app.db.models import (
    Conversation, ConversationStatus, Escalation, Message,
    MessageDirection, OdooSyncQueue, Platform, SenderType, SyncStatus, SyncType,
)
from app import agent
from app import sender as msg_sender
from app import escalation

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
        logger.info("Webhook verified successfully")
        return int(hub_challenge)
    logger.warning("Webhook verification failed: mode=%s, token=%s", hub_mode, hub_verify_token)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_hub_signature_256: str = Header(None, alias="x-hub-signature-256"),
):
    body = await request.body()
    if settings.meta_app_secret:
        if not _verify_signature(body, x_hub_signature_256):
            logger.warning("Invalid webhook signature — rejecting request")
            raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    obj = payload.get("object")
    if obj not in ("page", "instagram"):
        logger.debug("Ignoring webhook object type: %s", obj)
        return {"status": "ignored"}

    entries = payload.get("entry", [])
    for entry in entries:
        messaging_list = entry.get("messaging") or entry.get("messages", [])
        for event in messaging_list:
            await _process_message_event(event, obj, session)

    return {"status": "ok"}


async def _process_message_event(event: dict, object_type: str, session: AsyncSession) -> None:
    platform = Platform.INSTAGRAM if object_type == "instagram" else Platform.MESSENGER

    sender = event.get("sender", {})
    sender_id = sender.get("id")
    if not sender_id:
        return

    message = event.get("message", {})
    message_id = message.get("mid")
    message_text = message.get("text")

    if not message_text:
        postback = event.get("postback", {})
        if postback.get("payload"):
            message_text = postback["payload"]
        else:
            return

    if message.get("is_echo"):
        return

    logger.info("Incoming message: platform=%s sender=%s text='%s'",
        platform.value, sender_id, message_text[:100])

    # Deduplication
    if message_id:
        existing = await session.execute(
            select(Message).where(Message.platform_message_id == message_id))
        if existing.scalar_one_or_none():
            logger.debug("Duplicate message %s — skipping", message_id)
            return

    # Find or create conversation
    conversation = await _get_or_create_conversation(session, platform, sender_id)

    # Store inbound message
    inbound_msg = Message(
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        sender_type=SenderType.CUSTOMER,
        content=message_text,
        platform_message_id=message_id,
    )
    session.add(inbound_msg)
    await session.flush()

    logger.info("Stored message: conversation=%s message=%s", conversation.id, inbound_msg.id)

    # --- Full Pipeline ---

    # Typing indicator
    await msg_sender.send_typing_indicator(sender_id)

    # Get history for context
    history = await agent.get_conversation_history(conversation.id, session)

    # Classify + respond via Claude
    response = await agent.classify_and_respond(message_text, history)

    # Update conversation
    conversation.current_tier = response.tier
    conversation.intent_category = response.category

    # Store outbound reply
    outbound_msg = Message(
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND,
        sender_type=SenderType.BOT,
        content=response.reply,
        claude_classification={
            "tier": response.tier, "category": response.category,
            "confidence": response.confidence,
            "escalation_reason": response.escalation_reason,
        },
    )
    session.add(outbound_msg)

    # Send reply to customer
    sent = await msg_sender.send_reply(platform, sender_id, response.reply)
    if not sent:
        logger.error("Failed to send reply for conversation %s", conversation.id)

    # Handle escalation
    if response.tier == 3 or (response.tier == 2 and response.collected_data):
        conversation.status = ConversationStatus.ESCALATED
        esc = Escalation(
            conversation_id=conversation.id,
            tier=response.tier,
            reason=response.escalation_reason or f"Tier {response.tier}: {response.category}",
            collected_data=response.collected_data or None,
        )
        session.add(esc)
        await session.flush()
        await escalation.notify_staff(conversation, esc)

        # Queue for Odoo sync
        if response.category == "order" and response.collected_data:
            session.add(OdooSyncQueue(
                conversation_id=conversation.id, sync_type=SyncType.SALE_ORDER,
                payload=response.collected_data, status=SyncStatus.PENDING))
        elif response.category == "reservation" and response.collected_data:
            session.add(OdooSyncQueue(
                conversation_id=conversation.id, sync_type=SyncType.RESERVATION,
                payload=response.collected_data, status=SyncStatus.PENDING))

    await session.flush()


async def _get_or_create_conversation(
    session: AsyncSession, platform: Platform, sender_id: str,
) -> Conversation:
    result = await session.execute(
        select(Conversation).where(
            Conversation.platform == platform,
            Conversation.platform_sender_id == sender_id,
            Conversation.status == ConversationStatus.ACTIVE,
        ).order_by(Conversation.updated_at.desc()).limit(1)
    )
    conversation = result.scalar_one_or_none()
    if conversation:
        conversation.updated_at = datetime.now(timezone.utc)
        return conversation

    conversation = Conversation(
        platform=platform, platform_sender_id=sender_id,
        status=ConversationStatus.ACTIVE, current_tier=1,
    )
    session.add(conversation)
    await session.flush()
    logger.info("New conversation: %s (platform=%s, sender=%s)",
        conversation.id, platform.value, sender_id)
    return conversation


def _verify_signature(body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected_sig = signature_header[7:]
    actual_sig = hmac.new(
        settings.meta_app_secret.encode("utf-8"), body, hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_sig, actual_sig)
