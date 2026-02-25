"""
FastAPI webhook-сервер.

Регистрирует все эндпоинты и запускает uvicorn.

Telegram webhook верифицируется через X-Telegram-Bot-Api-Secret-Token.
Это происходит автоматически в aiogram SimpleRequestHandler —
он сравнивает заголовок с WEBHOOK_SECRET_TOKEN из настроек.
"""
from __future__ import annotations
import logging
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.core.config import settings
from app.api.health import router as health_router
from app.api.webhooks import router as payment_webhook_router
from app.api.status import router as status_router

logger = logging.getLogger(__name__)


async def start_webhook(bot: Bot, dp: Dispatcher) -> None:
    webhook_url = f"{settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}"

    await bot.set_webhook(
        url=webhook_url,
        secret_token=settings.WEBHOOK_SECRET_TOKEN or None,
        drop_pending_updates=True,
        allowed_updates=dp.resolve_used_update_types(),
    )
    logger.info(f"✅ Webhook set: {webhook_url}")
    if settings.WEBHOOK_SECRET_TOKEN:
        logger.info("🔒 Webhook secret token активен")
    else:
        logger.warning("⚠️ WEBHOOK_SECRET_TOKEN не задан — webhook не защищён")

    app = FastAPI(
        title="VPS Shop Bot",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Сохраняем bot в state для payment webhooks
    app.state.bot = bot

    # Роутеры
    app.include_router(health_router)
    app.include_router(payment_webhook_router)
    app.include_router(status_router)

    # ── Telegram webhook — aiogram обрабатывает верификацию секрета ──
    # SimpleRequestHandler автоматически проверяет заголовок
    # X-Telegram-Bot-Api-Secret-Token если secret_token задан.
    # При несоответствии возвращает 403 до передачи апдейта в диспетчер.
    handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.WEBHOOK_SECRET_TOKEN or None,
    )
    handler.register(app, path=settings.WEBHOOK_PATH)

    config = uvicorn.Config(
        app=app,
        host=settings.WEBHOOK_HOST,
        port=settings.WEBHOOK_PORT,
        log_level="warning",
        access_log=False,
        server_header=False,   # не раскрываем версию uvicorn
    )
    server = uvicorn.Server(config)
    logger.info(f"🌐 Listening on {settings.WEBHOOK_HOST}:{settings.WEBHOOK_PORT}")
    await server.serve()
