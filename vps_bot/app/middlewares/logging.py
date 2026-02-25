from __future__ import annotations
import logging
import time
from typing import Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        t0 = time.perf_counter()
        result = await handler(event, data)
        elapsed = (time.perf_counter() - t0) * 1000

        if isinstance(event, Message) and user:
            text = (event.text or "")[:60]
            logger.debug(f"[{user.id}] {text!r} → {elapsed:.0f}ms")

        return result
