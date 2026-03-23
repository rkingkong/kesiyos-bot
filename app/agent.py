"""
Kesiyos Bot — Agent (Claude API Integration)

Classifies incoming customer messages and generates responses.
Uses the Kesiyos knowledge base as system context.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_knowledge_base: str = ""


def _load_knowledge_base() -> str:
    global _knowledge_base
    if _knowledge_base:
        return _knowledge_base
    kb_path = settings.knowledge_base_path
    if kb_path.exists():
        _knowledge_base = kb_path.read_text(encoding="utf-8")
        logger.info("Knowledge base loaded: %d characters", len(_knowledge_base))
    else:
        _knowledge_base = "No knowledge base available."
        logger.error("Knowledge base not found at %s", kb_path)
    return _knowledge_base


@dataclass
class AgentResponse:
    tier: int = 1
    category: str = "unknown"
    reply: str = ""
    escalation_reason: str = ""
    collected_data: dict = field(default_factory=dict)
    confidence: float = 1.0


SYSTEM_PROMPT_TEMPLATE = """Eres el asistente virtual de Kesiyos, un restaurante guatemalteco.
Tu trabajo es atender a los clientes que escriben por Facebook Messenger e Instagram.

## Reglas fundamentales:
- Responde SIEMPRE en español, a menos que el cliente escriba en otro idioma.
- Trata al cliente de "usted" — tono amigable pero formal.
- Sé conciso — los mensajes deben ser cortos y directos (máximo 3-4 oraciones por respuesta).
- NUNCA inventes información que no esté en la base de conocimiento.
- Si no estás seguro de algo, escala al equipo humano.
- Usa emojis con moderación — máximo 1-2 por mensaje.

## Clasificación de mensajes:
Clasifica cada mensaje del cliente en uno de estos 3 niveles:

**Tier 1 — Respuesta automática:** Preguntas sobre menú, precios, horario, ubicación, delivery, métodos de pago, opciones para niños, salsas. Responde directamente.

**Tier 2 — Recopilar info y escalar:** Pedidos, reservaciones, preguntas sobre el programa de lealtad. Recopila la información necesaria (nombre, lo que desean, fecha/hora si es reservación, dirección si es delivery) y luego escala.

**Tier 3 — Escalar inmediatamente:** Quejas, reclamos, alergias, catering/eventos grandes, empleo, proveedores, facturas, problemas con pedidos existentes, cualquier cosa fuera de tu conocimiento.

## Para pedidos (Tier 2), recopila:
- Qué desea ordenar (producto, cantidad, personalización)
- Si es para comer aquí, para llevar, o delivery
- Si es delivery: dirección de entrega
- Nombre del cliente

## Para reservaciones (Tier 2), recopila:
- Nombre
- Fecha y hora
- Número de personas
- Alguna nota especial

## Formato de respuesta:
Responde ÚNICAMENTE con un JSON válido, sin texto adicional, sin markdown:
{{"tier": 1, "category": "menu", "reply": "Tu mensaje al cliente aquí", "escalation_reason": "", "collected_data": {{}}, "confidence": 0.95}}

Categorías válidas: menu, hours, location, delivery, payment, loyalty, kids, order, reservation, complaint, employment, catering, billing, other

## Base de conocimiento de Kesiyos:

{knowledge_base}
"""


async def classify_and_respond(
    message_text: str,
    conversation_history: list[dict] | None = None,
) -> AgentResponse:
    knowledge_base = _load_knowledge_base()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(knowledge_base=knowledge_base)
    messages = []
    if conversation_history:
        for msg in conversation_history[-10:]:
            role = "user" if msg["role"] == "customer" else "assistant"
            messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": message_text})
    try:
        response = await _call_claude(system_prompt, messages)
        return _parse_response(response)
    except Exception as e:
        logger.error("Claude API error: %s", str(e), exc_info=True)
        return AgentResponse(
            tier=3, category="other",
            reply="¡Gracias por escribirnos! En un momento uno de nuestros colaboradores le atenderá.",
            escalation_reason=f"Claude API error: {str(e)}", confidence=0.0,
        )


async def _call_claude(system_prompt: str, messages: list[dict]) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": messages,
            },
        )
        if response.status_code != 200:
            raise Exception(f"Claude API returned {response.status_code}: {response.text}")
        data = response.json()
        text_parts = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block["text"])
        return "\n".join(text_parts)


def _parse_response(raw_response: str) -> AgentResponse:
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1]).strip()
    try:
        data = json.loads(cleaned)
        return AgentResponse(
            tier=data.get("tier", 1), category=data.get("category", "other"),
            reply=data.get("reply", ""), escalation_reason=data.get("escalation_reason", ""),
            collected_data=data.get("collected_data", {}), confidence=data.get("confidence", 0.5),
        )
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse Claude response as JSON: %s", str(e))
        return AgentResponse(tier=1, category="other", reply=raw_response.strip(), confidence=0.3)


async def get_conversation_history(conversation_id, session) -> list[dict]:
    from sqlalchemy import select
    from app.db.models import Message, SenderType
    result = await session.execute(
        select(Message).where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc()).limit(20)
    )
    messages = result.scalars().all()
    history = []
    for msg in messages:
        role = "customer" if msg.sender_type == SenderType.CUSTOMER else "bot"
        history.append({"role": role, "content": msg.content})
    return history
