"""
Kesiyos Bot — Message Sender
Sends replies back to customers via the Meta Graph API.
"""

import logging
import httpx
from app.config import settings
from app.db.models import Platform

logger = logging.getLogger(__name__)
GRAPH_API_URL = "https://graph.facebook.com/v21.0/me/messages"


async def send_reply(platform: Platform, recipient_id: str, text: str) -> bool:
    if not settings.meta_page_access_token:
        logger.error("Cannot send message — META_PAGE_ACCESS_TOKEN not configured")
        return False
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                GRAPH_API_URL,
                params={"access_token": settings.meta_page_access_token},
                json=payload,
            )
            if response.status_code == 200:
                data = response.json()
                logger.info("Message sent: platform=%s recipient=%s message_id=%s",
                    platform.value, recipient_id, data.get("message_id", "unknown"))
                return True
            else:
                error = response.json().get("error", {})
                logger.error("Failed to send message: platform=%s recipient=%s status=%d error=%s",
                    platform.value, recipient_id, response.status_code, error.get("message", response.text))
                return False
    except httpx.TimeoutException:
        logger.error("Timeout sending message to %s on %s", recipient_id, platform.value)
        return False
    except Exception as e:
        logger.error("Error sending message: %s", str(e), exc_info=True)
        return False


async def send_typing_indicator(recipient_id: str, action: str = "typing_on") -> None:
    if not settings.meta_page_access_token:
        return
    payload = {"recipient": {"id": recipient_id}, "sender_action": action}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(GRAPH_API_URL,
                params={"access_token": settings.meta_page_access_token}, json=payload)
    except Exception:
        pass
