"""
VPS Provisioning Service.

Создаёт или продлевает VPS после подтверждения оплаты.
Включает антифрод, реферальные бонусы и уведомления в канал.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from aiogram import Bot
from app.core.config import settings, TARIFFS
from app.core.database import AsyncSessionLocal
from app.repositories.vps import VpsRepository
from app.repositories.user import PaymentRepository
from app.models import PaymentStatus
from app.services.proxmox import proxmox_service, generate_password
from app.services.n8n import n8n_notify
from app.services.notify import notify_new_vps
from app.services.antifrod import check_duplicate_payment

logger = logging.getLogger(__name__)


async def provision_vps(
    bot: Bot,
    telegram_id: int,
    tariff_id: str,
    payment_external_id: str,
    renew_vps_id: int | None = None,
) -> None:
    """Главная функция: создать или продлить VPS после оплаты."""
    tariff = TARIFFS[tariff_id]

    # Антифрод — предотвращаем двойную обработку одного платежа
    try:
        await check_duplicate_payment(payment_external_id)
    except Exception:
        logger.info(f"Duplicate payment processing blocked: {payment_external_id}")
        return

    async with AsyncSessionLocal() as session:
        vps_repo = VpsRepository(session)
        pay_repo = PaymentRepository(session)

        try:
            # ── Продление ────────────────────────────────────
            if renew_vps_id:
                vps = await vps_repo.get_by_id(renew_vps_id)
                if not vps or vps.telegram_id != telegram_id:
                    raise ValueError("VPS не найден или не принадлежит пользователю")

                base = max(vps.expires_at, datetime.utcnow())
                new_exp = base + timedelta(days=30)
                await vps_repo.extend(renew_vps_id, new_exp)

                payment = await pay_repo.get_by_external_id(payment_external_id)
                if payment:
                    await pay_repo.set_status(payment.id, PaymentStatus.PAID)

                await n8n_notify("vps.renewed", {
                    "telegram_id": telegram_id,
                    "ip": vps.ip,
                    "tariff": tariff_id,
                    "expires_at": new_exp.isoformat(),
                })

                await bot.send_message(
                    telegram_id,
                    f"✅ <b>Сервер продлён на 30 дней!</b>\n\n"
                    f"🌐 IP: <code>{vps.ip}</code>\n"
                    f"📅 Активен до: <b>{new_exp.strftime('%d.%m.%Y')}</b>\n\n"
                    f"Управляй сервером: /start → Мои серверы",
                )
                return

            # ── Создание нового VPS ──────────────────────────
            # Берём свободный IP
            ip = await vps_repo.acquire_ip()
            if not ip:
                raise RuntimeError(
                    "Нет свободных IP адресов.\n"
                    f"Обратись в поддержку: {settings.SUPPORT_USERNAME}"
                )

            vmid = await proxmox_service.next_vmid()
            hostname = f"vps-{telegram_id}-{vmid}"
            password = generate_password()
            expires_at = datetime.utcnow() + timedelta(days=30)

            # Создаём LXC контейнер в Proxmox
            await proxmox_service.create_lxc(vmid, hostname, ip, password, tariff)

            # Сохраняем в БД
            vps = await vps_repo.create(
                telegram_id=telegram_id,
                vmid=vmid,
                hostname=hostname,
                ip=ip,
                password=password,
                tariff=tariff_id,
                expires_at=expires_at,
            )

            # Помечаем платёж как оплаченный
            payment = await pay_repo.get_by_external_id(payment_external_id)
            if payment:
                await pay_repo.set_status(payment.id, PaymentStatus.PAID)
                currency = payment.currency
                amount = float(payment.amount)
            else:
                currency = "?"
                amount = 0

            # ── Реферальный бонус ─────────────────────────
            if settings.REFERRAL_ENABLED:
                await _pay_referral_bonus(bot, telegram_id, currency, amount)

            # ── Уведомления ───────────────────────────────
            from app.repositories.user import UserRepository
            async with AsyncSessionLocal() as s2:
                user = await UserRepository(s2).get_by_telegram_id(telegram_id)

            await n8n_notify("vps.created", {
                "telegram_id": telegram_id,
                "ip": ip,
                "tariff": tariff_id,
                "vmid": vmid,
                "amount": amount,
                "currency": currency,
                "expires_at": expires_at.isoformat(),
            })

            await notify_new_vps(
                bot, telegram_id,
                user.username if user else None,
                tariff_id, ip, amount, currency,
            )

            # ── Сообщение пользователю ────────────────────
            await bot.send_message(
                telegram_id,
                f"🎉 <b>Твой сервер готов!</b>\n\n"
                f"📦 Тариф: <b>{tariff['name']}</b>\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"🌐 IP: <code>{ip}</code>\n"
                f"👤 Логин: <code>root</code>\n"
                f"🔑 Пароль: <code>{password}</code>\n"
                f"━━━━━━━━━━━━━━━━━\n\n"
                f"🔌 SSH: <code>ssh root@{ip}</code>\n\n"
                f"📅 Активен до: <b>{expires_at.strftime('%d.%m.%Y')}</b>\n\n"
                f"📖 Управляй сервером: /start → Мои серверы",
            )

            logger.info(f"VPS #{vps.id} ({ip}) created for user {telegram_id}")

        except Exception as exc:
            logger.exception(f"provision_vps FAILED for {telegram_id}: {exc}")

            # Освобождаем IP если он был взят но VPS не создан
            try:
                if 'ip' in locals() and ip:
                    async with AsyncSessionLocal() as s:
                        await VpsRepository(s).release_ip(ip)
            except Exception:
                pass

            # Помечаем платёж как ошибочный
            try:
                async with AsyncSessionLocal() as s:
                    p = await PaymentRepository(s).get_by_external_id(payment_external_id)
                    if p and p.status.value == "pending":
                        await PaymentRepository(s).set_status(p.id, PaymentStatus.FAILED)
            except Exception:
                pass

            # Сообщаем пользователю
            await bot.send_message(
                telegram_id,
                f"❌ <b>Ошибка при создании сервера</b>\n\n"
                f"Деньги не списаны зря — обратись в поддержку и мы всё исправим.\n"
                f"📞 {settings.SUPPORT_USERNAME}\n\n"
                f"<i>Код ошибки: {type(exc).__name__}</i>",
            )

            # Уведомляем администраторов
            from app.services.notify import notify_error
            await notify_error(bot, f"provision_vps failed for {telegram_id}", str(exc))


async def _pay_referral_bonus(
    bot: Bot,
    telegram_id: int,
    currency: str,
    amount: float,
) -> None:
    """Начислить бонус рефереру при первой покупке реферала."""
    try:
        async with AsyncSessionLocal() as session:
            from app.services.referral import ReferralRepository
            repo = ReferralRepository(session)

            referrer_id = await repo.get_referrer(telegram_id)
            if not referrer_id:
                return

            ref_result = await session.execute(
                __import__('sqlalchemy', fromlist=['select']).select(
                    __import__('app.services.referral', fromlist=['Referral']).Referral
                ).where(
                    __import__('app.services.referral', fromlist=['Referral']).Referral.referred_id == telegram_id
                )
            )
            ref = ref_result.scalar_one_or_none()
            if not ref or ref.bonus_paid:
                return

            # Выдаём бонус
            is_usdt = currency == "USDT"
            bonus_rub = settings.REFERRAL_BONUS_RUB if not is_usdt else 0
            bonus_usdt = settings.REFERRAL_BONUS_USDT if is_usdt else 0

            await repo.add_balance(referrer_id, rub=bonus_rub, usdt=bonus_usdt)
            await repo.mark_bonus_paid(telegram_id, bonus_usdt if is_usdt else bonus_rub, currency)

        # Уведомляем реферера
        bonus_str = f"{bonus_usdt} USDT" if is_usdt else f"{bonus_rub:.0f} ₽"
        await bot.send_message(
            referrer_id,
            f"🎉 <b>Реферальный бонус!</b>\n\n"
            f"Твой реферал купил VPS!\n"
            f"На твой бонусный баланс начислено: <b>{bonus_str}</b>\n\n"
            f"Проверь баланс: /ref",
        )
        logger.info(f"Referral bonus paid: {bonus_str} to {referrer_id}")

    except Exception as e:
        logger.error(f"Referral bonus failed: {e}")
