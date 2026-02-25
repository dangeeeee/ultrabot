from __future__ import annotations
import logging
from typing import Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from app.core.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)
WINDOW = 60  # секунд


class RateLimitMiddleware(BaseMiddleware):
    """Ограничение: не более N сообщений в минуту на пользователя."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        # Admins bypass rate limit
        if user.id in settings.ADMIN_IDS:
            return await handler(event, data)

        redis = await get_redis()
        key = f"rl:{user.id}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, WINDOW)

        limit = settings.RATE_LIMIT_MESSAGES
        if count > limit:
            if isinstance(event, Message):
                await event.answer("⏳ Слишком много запросов. Подожди минуту.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⏳ Подожди немного.", show_alert=True)
            return None

        return await handler(event, data)
