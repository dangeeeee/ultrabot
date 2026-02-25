import logging
import logging.handlers
import os
from app.core.config import settings


def setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if settings.LOG_ROTATION_ENABLED:
        file_handler = logging.handlers.RotatingFileHandler(
            filename="logs/bot.log",
            maxBytes=settings.LOG_MAX_SIZE_MB * 1024 * 1024,
            backupCount=settings.LOG_MAX_FILES,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        handlers.append(file_handler)

    for h in handlers:
        h.setFormatter(fmt)

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        handlers=handlers,
    )

    # Убираем лишний шум от библиотек
    for noisy in ("aiohttp", "aiogram.event", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
