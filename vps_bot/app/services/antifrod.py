"""
Антифрод сервис.

Проверки перед созданием VPS:
1. Лимит VPS на пользователя (MAX_VPS_PER_USER)
2. Повторные попытки оплаты в короткий срок (Redis TTL)
3. Проверка что платёж не задублирован

Все отказы логируются и отправляются в n8n.
"""
from __future__ import annotations
import logging
from app.core.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class AntifrodError(Exception):
    """Ошибка антифрода — транслируется пользователю."""
    pass


async def check_vps_limit(telegram_id: int) -> None:
    """Проверить что пользователь не превысил лимит VPS."""
    from app.core.database import AsyncSessionLocal
    from app.repositories.vps import VpsRepository

    async with AsyncSessionLocal() as session:
        vps_list = await VpsRepository(session).get_user_vps(telegram_id)

    if len(vps_list) >= settings.MAX_VPS_PER_USER:
        logger.warning(f"Antifrod: user {telegram_id} reached VPS limit ({len(vps_list)})")
        raise AntifrodError(
            f"❌ Достигнут лимит серверов\n\n"
            f"У тебя уже {len(vps_list)} серверов (максимум {settings.MAX_VPS_PER_USER}).\n"
            f"Удали неиспользуемые серверы или обратись в поддержку."
        )


async def check_payment_cooldown(telegram_id: int) -> None:
    """Антиспам: не более N платежей в минуту."""
    redis = await get_redis()
    key = f"pay_cd:{telegram_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)

    if count > settings.RATE_LIMIT_PAYMENTS:
        logger.warning(f"Antifrod: payment rate limit for user {telegram_id}")
        raise AntifrodError(
            "⏳ Слишком много попыток оплаты.\n\nПодожди минуту и попробуй снова."
        )


async def check_duplicate_payment(external_id: str) -> None:
    """Проверить что этот инвойс не обрабатывается прямо сейчас."""
    redis = await get_redis()
    lock_key = f"pay_lock:{external_id}"
    # SET NX EX — атомарная блокировка на 5 минут
    acquired = await redis.set(lock_key, "1", nx=True, ex=300)
    if not acquired:
        logger.warning(f"Antifrod: duplicate payment processing for {external_id}")
        raise AntifrodError(
            "⚠️ Этот платёж уже обрабатывается. Подожди пару минут."
        )


async def run_pre_payment_checks(telegram_id: int) -> None:
    """Все проверки перед созданием инвойса."""
    await check_payment_cooldown(telegram_id)
    await check_vps_limit(telegram_id)
