"""
Security Middleware:
- Проверяет бан пользователя
- Создаёт запись в БД при первом обращении + уведомляет n8n
- Блокирует ботов (is_bot=True)
"""
from __future__ import annotations
import logging
from typing import Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.repositories.user import UserRepository

logger = logging.getLogger(__name__)


class SecurityMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        # Блок ботов
        if user.is_bot:
            return None

        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)

            # get_or_create возвращает (user, is_new)
            db_user, is_new = await repo.get_or_create(
                telegram_id=user.id,
                username=user.username,
                full_name=user.full_name,
            )

            if db_user.is_banned:
                if isinstance(event, Message):
                    await event.answer("🚫 Ваш аккаунт заблокирован. Обратитесь в поддержку.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚫 Аккаунт заблокирован.", show_alert=True)
                return None

        # Уведомляем n8n о новом пользователе
        if is_new:
            try:
                from app.services.n8n import n8n_notify
                await n8n_notify("user.registered", {
                    "telegram_id": user.id,
                    "username": user.username or "",
                    "full_name": user.full_name or "",
                })
            except Exception:
                pass

        return await handler(event, data)
