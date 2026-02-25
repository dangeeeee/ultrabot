"""
Проверки при старте бота:
1. Тест подключения к Proxmox
2. Заполнение IP пула из .env если пул в БД пуст
"""
from __future__ import annotations
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


async def run_startup_checks() -> None:
    await _test_proxmox()
    await _init_ip_pool()


async def _test_proxmox() -> None:
    if not settings.PROXMOX_HOST:
        logger.warning("⚠️  PROXMOX_HOST не задан — пропускаю проверку")
        return
    try:
        from app.services.proxmox import proxmox_service
        st = await proxmox_service.node_status()
        logger.info(
            f"✅ Proxmox OK — CPU {st['cpu_pct']}% | "
            f"RAM {st['mem_used_gb']}/{st['mem_total_gb']} GB"
        )
    except Exception as e:
        logger.error(f"❌ Proxmox недоступен: {e}")
        logger.error("   Проверь PROXMOX_HOST, PROXMOX_TOKEN_NAME, PROXMOX_TOKEN_VALUE в .env")


async def _init_ip_pool() -> None:
    if not settings.PROXMOX_IP_POOL:
        logger.warning("⚠️  PROXMOX_IP_POOL пуст — VPS создать не получится")
        return

    from app.core.database import AsyncSessionLocal
    from app.models import IpPool
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as session:
        count_result = await session.execute(select(func.count(IpPool.id)))
        existing = count_result.scalar_one()

        if existing == 0:
            # Первый запуск — заполняем пул из .env
            for ip in settings.PROXMOX_IP_POOL:
                session.add(IpPool(ip=ip.strip(), in_use=False))
            await session.commit()
            logger.info(f"✅ IP пул заполнен: {len(settings.PROXMOX_IP_POOL)} адресов")
        else:
            # Добавляем новые IP если их нет в пуле
            added = 0
            for ip in settings.PROXMOX_IP_POOL:
                exists = await session.execute(
                    select(IpPool).where(IpPool.ip == ip.strip())
                )
                if not exists.scalar_one_or_none():
                    session.add(IpPool(ip=ip.strip(), in_use=False))
                    added += 1
            if added:
                await session.commit()
                logger.info(f"✅ Добавлено {added} новых IP в пул")
            logger.info(f"✅ IP пул: {existing + added} адресов")
