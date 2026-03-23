"""
Kesiyos Bot — Escalation Notifier
Sends WhatsApp messages to staff when conversations need human attention.
"""

import logging
from datetime import datetime, timezone
import httpx
from app.config import settings
from app.db.models import Conversation, Escalation, Platform

logger = logging.getLogger(__name__)
WHATSAPP_API_URL = "https://graph.facebook.com/v21.0/{phone_id}/messages"


async def notify_staff(conversation: Conversation, escalation: Escalation) -> bool:
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        logger.warning("WhatsApp not configured — escalation alert skipped")
        return False
    if not settings.escalation_staff_phones:
        logger.warning("No staff phone numbers configured — escalation alert skipped")
        return False
    alert_text = _build_alert_message(conversation, escalation)
    any_success = False
    for phone in settings.escalation_staff_phones:
        success = await _send_whatsapp_message(phone, alert_text)
        if success:
            any_success = True
    if any_success:
        escalation.staff_notified_at = datetime.now(timezone.utc)
        logger.info("Staff notified for conversation %s", conversation.id)
    else:
        logger.error("Failed to notify ANY staff for conversation %s", conversation.id)
    return any_success


def _build_alert_message(conversation: Conversation, escalation: Escalation) -> str:
    platform_emoji = "📘" if conversation.platform == Platform.MESSENGER else "📷"
    platform_name = "Facebook Messenger" if conversation.platform == Platform.MESSENGER else "Instagram"
    tier_label = "⚡ Escalación inmediata" if escalation.tier == 3 else "📋 Info recopilada"
    lines = [
        f"{platform_emoji} *NUEVA ESCALACIÓN — {tier_label}*", "",
        f"📱 Plataforma: {platform_name}",
        f"👤 Cliente: {conversation.customer_name or 'Sin nombre'}",
        f"🆔 ID: {conversation.platform_sender_id}",
        f"📂 Categoría: {conversation.intent_category or 'No clasificada'}", "",
        f"📝 Razón: {escalation.reason}",
    ]
    if escalation.collected_data:
        lines.extend(["", "📦 *Datos recopilados:*"])
        for key, value in escalation.collected_data.items():
            lines.append(f"  • {key}: {value}")
    lines.extend(["", "👉 Responda al cliente desde Meta Business Suite."])
    return "\n".join(lines)


async def _send_whatsapp_message(phone_number: str, text: str) -> bool:
    url = WHATSAPP_API_URL.format(phone_id=settings.whatsapp_phone_number_id)
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": text},
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url,
                headers={"Authorization": f"Bearer {settings.whatsapp_access_token}",
                         "Content-Type": "application/json"},
                json=payload)
            if response.status_code == 200:
                logger.info("WhatsApp alert sent to %s", phone_number[-4:].rjust(len(phone_number), '*'))
                return True
            else:
                error = response.json().get("error", {})
                logger.error("WhatsApp send failed: %d — %s", response.status_code, error.get("message", response.text))
                return False
    except Exception as e:
        logger.error("WhatsApp send error: %s", str(e))
        return False
