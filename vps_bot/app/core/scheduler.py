import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from app.core.config import settings, TARIFFS

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone=settings.TZ)


async def _notify_expiring(bot: Bot) -> None:
    """Напоминания за 3 дня и 1 день до истечения."""
    from app.repositories.vps import VpsRepository
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        repo = VpsRepository(session)
        for days in (3, 1):
            rows = await repo.get_expiring(days)
            for vps in rows:
                t = TARIFFS.get(vps.tariff, {})
                emoji = "⚠️" if days == 3 else "🚨"
                text = (
                    f"{emoji} <b>Твой VPS истекает через {days} {'дня' if days == 3 else 'день'}!</b>\n\n"
                    f"🌐 IP: <code>{vps.ip}</code>\n"
                    f"📅 Истекает: <b>{vps.expires_at.strftime('%d.%m.%Y')}</b>\n\n"
                    f"💰 Продли сейчас:\n"
                    f"  • Карта РФ: <b>{t.get('price_rub', '?')} ₽</b>\n"
                    f"  • USDT: <b>{t.get('price_usdt', '?')}</b>\n\n"
                    f"👉 /start → Мои серверы → Продлить"
                )
                try:
                    await bot.send_message(vps.telegram_id, text)
                    await repo.mark_reminded(vps.id, days)
                except Exception as e:
                    logger.warning(f"Reminder failed for {vps.telegram_id}: {e}")


async def _delete_expired(bot: Bot) -> None:
    """Удаление истёкших VPS."""
    from app.repositories.vps import VpsRepository
    from app.services.proxmox import proxmox_service
    from app.core.database import AsyncSessionLocal
    from app.services.n8n import n8n_notify
    from app.services.notify import notify_vps_expired

    async with AsyncSessionLocal() as session:
        repo = VpsRepository(session)
        expired = await repo.get_expired()

    for vps in expired:
        try:
            await proxmox_service.delete_lxc(vps.vmid)
            async with AsyncSessionLocal() as session:
                await VpsRepository(session).mark_deleted(vps.id)
                await VpsRepository(session).release_ip(vps.ip)

            await n8n_notify("vps.expired", {
                "telegram_id": vps.telegram_id,
                "ip": vps.ip,
                "tariff": vps.tariff,
            })
            await notify_vps_expired(bot, vps.telegram_id, vps.ip, vps.tariff)

            try:
                await bot.send_message(
                    vps.telegram_id,
                    f"❌ <b>Сервер удалён</b>\n\n"
                    f"VPS <code>{vps.ip}</code> удалён — срок истёк.\n"
                    f"Купи новый: /start → Тарифы",
                )
            except Exception:
                pass

            logger.info(f"Deleted expired VPS #{vps.id} ({vps.ip})")
        except Exception as e:
            logger.error(f"Failed to delete expired VPS #{vps.id}: {e}")


async def _auto_backup(bot: Bot) -> None:
    """Автобекап PostgreSQL → Telegram."""
    from app.services.backup import make_backup
    await make_backup(bot)


async def start_scheduler(bot: Bot) -> None:
    scheduler.add_job(
        _notify_expiring,
        CronTrigger(hour="*/6"),
        args=[bot],
        id="notify_expiring",
        replace_existing=True,
    )
    scheduler.add_job(
        _delete_expired,
        CronTrigger(minute="*/30"),
        args=[bot],
        id="delete_expired",
        replace_existing=True,
    )
    if settings.AUTO_BACKUP_ENABLED:
        scheduler.add_job(
            _auto_backup,
            CronTrigger(hour=settings.AUTO_BACKUP_HOUR, minute=0),
            args=[bot],
            id="auto_backup",
            replace_existing=True,
        )
        logger.info(f"Auto-backup scheduled at {settings.AUTO_BACKUP_HOUR:02d}:00 UTC")

    scheduler.add_job(
        _run_autorenew,
        CronTrigger(hour="*/6"),
        args=[bot],
        id="autorenew",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("✅ Scheduler started (expiring/6h, delete/30min, autorenew/6h)")


async def _run_autorenew(bot: Bot) -> None:
    """Проверяем VPS с включённым автопродлением."""
    from app.services.autorenew import check_autorenew
    await check_autorenew(bot)
