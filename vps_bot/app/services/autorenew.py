"""
Автопродление VPS с бонусного реферального баланса.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from aiogram import Bot
from app.core.config import TARIFFS
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def try_autorenew_all(bot: Bot) -> None:
    """Пробуем автопродлить все истекающие VPS у юзеров с включённым autorenew."""
    from app.repositories.vps import VpsRepository
    from app.services.referral import ReferralRepository
    from app.models import Vps, VpsStatus
    from app.core.redis import get_redis
    from sqlalchemy import select

    now = datetime.utcnow()
    threshold = now + timedelta(hours=24)
    redis = await get_redis()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Vps)
            .where(Vps.status == VpsStatus.ACTIVE)
            .where(Vps.expires_at > now)
            .where(Vps.expires_at <= threshold)
        )
        expiring = result.scalars().all()

        for vps in expiring:
            # Проверяем флаг автопродления
            ar_enabled = await redis.get(f"autorenew:{vps.telegram_id}")
            if ar_enabled != "1":
                continue

            tariff = TARIFFS.get(vps.tariff, {})
            price_rub = float(tariff.get("price_rub", 0))
            if price_rub == 0:
                continue

            ref_repo = ReferralRepository(session)
            balance = await ref_repo.get_or_create_balance(vps.telegram_id)

            if float(balance.balance_rub) < price_rub:
                continue

            # Списываем и продлеваем
            balance.balance_rub = float(balance.balance_rub) - price_rub
            new_exp = max(vps.expires_at, now) + timedelta(days=30)
            await VpsRepository(session).extend(vps.id, new_exp)
            await session.commit()

            logger.info(f"Autorenew: VPS #{vps.id} ({vps.ip}) for user {vps.telegram_id}")

            try:
                await bot.send_message(
                    vps.telegram_id,
                    f"🔄 <b>Автопродление выполнено!</b>\n\n"
                    f"🌐 VPS: <code>{vps.ip}</code>\n"
                    f"💳 Списано с баланса: <b>{price_rub:.0f} ₽</b>\n"
                    f"📅 Активен до: <b>{new_exp.strftime('%d.%m.%Y')}</b>\n\n"
                    f"Остаток баланса: <b>{float(balance.balance_rub):.2f} ₽</b>",
                )
            except Exception:
                pass
