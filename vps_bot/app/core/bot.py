from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from app.core.config import settings
from app.middlewares.security import SecurityMiddleware
from app.middlewares.rate_limit import RateLimitMiddleware
from app.middlewares.logging import LoggingMiddleware

# Клиентские хендлеры
from app.handlers.client import start, tariffs, my_vps
from app.handlers.client.referral import router as referral_router
from app.handlers.client.language import router as language_router
from app.handlers.client.promo import router as promo_router
from app.handlers.client.autorenew import router as autorenew_router

# Платежи
from app.handlers.payments import cryptobot, yukassa

# Админ
from app.handlers.admin import panel, users, broadcast
from app.handlers.admin.promo import router as admin_promo_router


def create_bot() -> Bot:
    return Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    storage = RedisStorage.from_url(settings.REDIS_URL)
    dp = Dispatcher(storage=storage)

    # ── Middlewares ─────────────────────────────────────────
    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(SecurityMiddleware())
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(SecurityMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())

    # ── Client ──────────────────────────────────────────────
    dp.include_router(start.router)
    dp.include_router(language_router)
    dp.include_router(tariffs.router)
    dp.include_router(promo_router)        # должен быть ДО my_vps
    dp.include_router(my_vps.router)
    dp.include_router(referral_router)
    dp.include_router(autorenew_router)

    # ── Payments ────────────────────────────────────────────
    dp.include_router(cryptobot.router)
    dp.include_router(yukassa.router)

    # ── Admin ───────────────────────────────────────────────
    dp.include_router(panel.router)
    dp.include_router(users.router)
    dp.include_router(broadcast.router)
    dp.include_router(admin_promo_router)

    return dp
