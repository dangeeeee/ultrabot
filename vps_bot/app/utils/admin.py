"""
Утилиты для администраторов.

admin_only      — декоратор для хендлеров (Message + CallbackQuery)
is_admin        — простая проверка bool
require_admin   — фильтр aiogram для роутеров
"""
from __future__ import annotations
from functools import wraps
from typing import Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery, TelegramObject
from app.core.config import settings


def is_admin(telegram_id: int) -> bool:
    """Проверить является ли пользователь администратором."""
    return telegram_id in settings.ADMIN_IDS


def admin_only(func: Callable) -> Callable:
    """
    Декоратор для хендлеров Message и CallbackQuery.
    Блокирует доступ не-администраторам.

    Использование:
        @router.message(Command("admin"))
        @admin_only
        async def cmd_admin(message: Message) -> None: ...
    """
    @wraps(func)
    async def wrapper(event: Message | CallbackQuery, *args: Any, **kwargs: Any) -> Any:
        user_id = getattr(event.from_user, "id", None)
        if not user_id or not is_admin(user_id):
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ Нет доступа.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("⛔ Доступ запрещён.")
            return None
        return await func(event, *args, **kwargs)
    return wrapper


class AdminFilter(BaseFilter):
    """
    Фильтр для роутеров — пропускает только администраторов.

    Использование:
        router = Router()
        router.message.filter(AdminFilter())
    """
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = getattr(getattr(event, "from_user", None), "id", None)
        return bool(user_id and is_admin(user_id))
