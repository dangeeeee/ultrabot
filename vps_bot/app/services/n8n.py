"""
n8n Integration Service
─────────────────────────────────────────────────────────────────
Отправляет события из бота в n8n-воркфлоу через Webhook-триггеры.

Настройка в n8n:
1. Создай воркфлоу с нодой "Webhook" (POST)
2. Скопируй URL вида https://n8n.your-domain.com/webhook/vps-events
3. Поставь его в .env → N8N_WEBHOOK_URL
4. Опционально: поставь заголовок Authorization в N8N_API_KEY

События которые шлёт бот:
  - vps.created       — новый сервер куплен
  - vps.renewed       — сервер продлён
  - vps.expired       — сервер удалён по истечению
  - payment.received  — получен платёж
  - user.registered   — новый пользователь
  - user.banned       — пользователь заблокирован
"""
from __future__ import annotations
import logging
import aiohttp
from app.core.config import settings

logger = logging.getLogger(__name__)


async def n8n_notify(event: str, payload: dict) -> None:
    """Отправить событие в n8n. Ошибки не прерывают основной поток."""
    if not settings.N8N_WEBHOOK_URL:
        return

    data = {"event": event, **payload}
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.N8N_API_KEY:
        headers["Authorization"] = f"Bearer {settings.N8N_API_KEY}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                settings.N8N_WEBHOOK_URL,
                json=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status not in (200, 201):
                    logger.warning(f"n8n responded {resp.status} for event '{event}'")
                else:
                    logger.debug(f"n8n notified: {event}")
    except Exception as e:
        logger.warning(f"n8n notify failed ({event}): {e}")
