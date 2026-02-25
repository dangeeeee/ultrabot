"""
Глобальный обработчик ошибок.
Ловит все необработанные исключения, логирует их
и отправляет красивое сообщение пользователю.
Критические ошибки отправляет администраторам.
"""
from __future__ import annotations
import logging
import traceback
from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramBadRequest,
    TelegramRetryAfter,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


def setup_error_handlers(dp: Dispatcher, bot: Bot) -> None:
    @dp.errors()
    async def handle_error(event: ErrorEvent) -> bool:
        exc = event.exception
        update = event.update

        # Получаем telegram_id и chat_id из апдейта
        chat_id: int | None = None
        user_id: int | None = None
        try:
            if update.message:
                chat_id = update.message.chat.id
                user_id = update.message.from_user.id if update.message.from_user else None
            elif update.callback_query:
                chat_id = update.callback_query.message.chat.id
                user_id = update.callback_query.from_user.id
        except Exception:
            pass

        # ── Известные ошибки Telegram ────────────────────────

        if isinstance(exc, TelegramForbiddenError):
            # Юзер заблокировал бота
            logger.info(f"User {user_id} blocked the bot")
            return True

        if isinstance(exc, TelegramNotFound):
            logger.warning(f"Chat not found: {chat_id}")
            return True

        if isinstance(exc, TelegramRetryAfter):
            logger.warning(f"Rate limit: retry after {exc.retry_after}s")
            return True

        if isinstance(exc, TelegramBadRequest):
            msg = str(exc).lower()
            # Игнорируем "message is not modified"
            if "message is not modified" in msg:
                return True
            logger.warning(f"TelegramBadRequest: {exc}")
            return True

        # ── Неизвестная ошибка ───────────────────────────────

        tb = traceback.format_exc()
        logger.error(f"Unhandled error [{type(exc).__name__}]: {exc}\n{tb}")

        # Сообщаем пользователю
        if chat_id:
            try:
                await bot.send_message(
                    chat_id,
                    "⚠️ Что-то пошло не так. Попробуй ещё раз или напиши в поддержку.",
                )
            except Exception:
                pass

        # Уведомляем администраторов о критических ошибках
        short_tb = tb[-1500:] if len(tb) > 1500 else tb
        admin_msg = (
            f"🚨 <b>Unhandled Error</b>\n\n"
            f"<b>Type:</b> {type(exc).__name__}\n"
            f"<b>User:</b> {user_id}\n"
            f"<b>Error:</b> {str(exc)[:300]}\n\n"
            f"<pre>{short_tb}</pre>"
        )
        for admin_id in settings.ADMIN_IDS:
            try:
                await bot.send_message(admin_id, admin_msg)
            except Exception:
                pass

        return True
