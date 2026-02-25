"""
Уведомления администраторам о важных событиях.

При каждой покупке/ошибке отправляем в NOTIFY_CHANNEL_ID (и топик если задан).
"""
from __future__ import annotations
import logging
from datetime import datetime
from aiogram import Bot
from app.core.config import settings, TARIFFS

logger = logging.getLogger(__name__)


async def notify_new_vps(
    bot: Bot,
    telegram_id: int,
    username: str | None,
    tariff_id: str,
    ip: str,
    amount: float,
    currency: str,
) -> None:
    if not settings.NOTIFY_CHANNEL_ID:
        return

    t = TARIFFS.get(tariff_id, {})
    text = (
        f"🎉 <b>Новый VPS куплен!</b>\n\n"
        f"👤 Пользователь: @{username or '—'} (<code>{telegram_id}</code>)\n"
        f"📦 Тариф: <b>{t.get('name', tariff_id)}</b>\n"
        f"🌐 IP: <code>{ip}</code>\n"
        f"💰 Оплачено: <b>{amount} {currency}</b>\n"
        f"🕐 Время: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC"
    )
    await _send(bot, text)


async def notify_vps_expired(
    bot: Bot,
    telegram_id: int,
    ip: str,
    tariff_id: str,
) -> None:
    if not settings.NOTIFY_CHANNEL_ID:
        return

    t = TARIFFS.get(tariff_id, {})
    text = (
        f"⏰ <b>VPS истёк и удалён</b>\n\n"
        f"👤 Пользователь: <code>{telegram_id}</code>\n"
        f"📦 Тариф: {t.get('name', tariff_id)}\n"
        f"🌐 IP: <code>{ip}</code>"
    )
    await _send(bot, text)


async def notify_error(bot: Bot, description: str, detail: str = "") -> None:
    if not settings.NOTIFY_CHANNEL_ID:
        return

    text = (
        f"🚨 <b>Ошибка</b>\n\n"
        f"{description}\n"
        f"<pre>{detail[:500]}</pre>" if detail else f"🚨 <b>Ошибка</b>\n\n{description}"
    )
    await _send(bot, text)


async def _send(bot: Bot, text: str) -> None:
    try:
        kwargs: dict = {
            "chat_id": settings.NOTIFY_CHANNEL_ID,
            "text": text,
        }
        if settings.NOTIFY_TOPIC_ID:
            kwargs["message_thread_id"] = settings.NOTIFY_TOPIC_ID
        await bot.send_message(**kwargs)
    except Exception as e:
        logger.warning(f"Channel notification failed: {e}")
