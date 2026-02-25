"""
Команды администратора для управления промокодами.

/addpromo <CODE> <TYPE> <VALUE> [--uses N] [--expire YYYY-MM-DD] [--tariffs starter,pro]
  TYPE: percent | rub | usdt

Примеры:
  /addpromo SUMMER percent 20
  /addpromo FRIEND rub 100 --uses 50
  /addpromo VIP usdt 2 --tariffs pro --uses 10 --expire 2025-12-31

/promos — список активных промокодов
/delpromo <CODE> — деактивировать промокод
"""
from __future__ import annotations
import logging
from datetime import datetime
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app.core.database import AsyncSessionLocal
from app.services.promo import PromoRepository, PromoType
from app.utils.admin import admin_only

logger = logging.getLogger(__name__)
router = Router(name="admin_promo")

TYPE_MAP = {
    "percent": PromoType.PERCENT,
    "rub": PromoType.FIXED_RUB,
    "usdt": PromoType.FIXED_USDT,
}


@router.message(Command("addpromo"))
@admin_only
async def cmd_addpromo(message: Message) -> None:
    """
    /addpromo CODE TYPE VALUE [--uses N] [--expire YYYY-MM-DD] [--tariffs t1,t2] [--once 0/1]
    """
    parts = message.text.split()
    if len(parts) < 4:
        await message.answer(
            "📋 <b>Создание промокода</b>\n\n"
            "Использование:\n"
            "<code>/addpromo CODE TYPE VALUE [опции]</code>\n\n"
            "Типы:\n"
            "  <code>percent</code> — % скидки (напр: 20 = -20%)\n"
            "  <code>rub</code>     — скидка в рублях\n"
            "  <code>usdt</code>    — скидка в USDT\n\n"
            "Опции:\n"
            "  <code>--uses N</code>           лимит активаций (0=∞)\n"
            "  <code>--expire YYYY-MM-DD</code> дата истечения\n"
            "  <code>--tariffs t1,t2</code>    только для тарифов\n"
            "  <code>--once 0</code>           не ограничивать одним юзером\n\n"
            "Примеры:\n"
            "<code>/addpromo SUMMER percent 20</code>\n"
            "<code>/addpromo FRIEND rub 100 --uses 50</code>\n"
            "<code>/addpromo VIP usdt 2 --tariffs pro --uses 10</code>"
        )
        return

    code = parts[1].upper()
    type_str = parts[2].lower()
    try:
        value = float(parts[3])
    except ValueError:
        await message.answer("❌ VALUE должен быть числом")
        return

    if type_str not in TYPE_MAP:
        await message.answer(f"❌ Неизвестный тип: {type_str}\nДоступны: percent, rub, usdt")
        return

    # Парсим опции
    max_uses = 0
    expires_at = None
    only_tariffs = ""
    one_per_user = True

    i = 4
    while i < len(parts):
        opt = parts[i]
        if opt == "--uses" and i + 1 < len(parts):
            try:
                max_uses = int(parts[i + 1])
                i += 2
                continue
            except ValueError:
                pass
        elif opt == "--expire" and i + 1 < len(parts):
            try:
                expires_at = datetime.strptime(parts[i + 1], "%Y-%m-%d")
                i += 2
                continue
            except ValueError:
                await message.answer("❌ Формат даты: YYYY-MM-DD")
                return
        elif opt == "--tariffs" and i + 1 < len(parts):
            only_tariffs = parts[i + 1]
            i += 2
            continue
        elif opt == "--once" and i + 1 < len(parts):
            one_per_user = parts[i + 1] != "0"
            i += 2
            continue
        i += 1

    async with AsyncSessionLocal() as session:
        repo = PromoRepository(session)
        existing = await repo.get_by_code(code)
        if existing:
            await message.answer(f"❌ Промокод <code>{code}</code> уже существует")
            return

        promo = await repo.create(
            code=code,
            promo_type=TYPE_MAP[type_str],
            value=value,
            created_by=message.from_user.id,
            max_uses=max_uses,
            expires_at=expires_at,
            only_tariffs=only_tariffs,
            one_per_user=one_per_user,
        )

    uses_str = f"{max_uses}" if max_uses > 0 else "∞"
    expire_str = expires_at.strftime("%d.%m.%Y") if expires_at else "∞"
    tariff_str = only_tariffs if only_tariffs else "все"
    once_str = "1 раз на юзера" if one_per_user else "неограниченно"

    await message.answer(
        f"✅ <b>Промокод создан!</b>\n\n"
        f"🎫 Код: <code>{code}</code>\n"
        f"💰 Скидка: <b>{value:.0f}"
        f"{'%' if type_str == 'percent' else ' ₽' if type_str == 'rub' else ' USDT'}</b>\n"
        f"🔢 Лимит: <b>{uses_str}</b>\n"
        f"📅 Истекает: <b>{expire_str}</b>\n"
        f"📦 Тарифы: <b>{tariff_str}</b>\n"
        f"👤 Повторное использование: <b>{once_str}</b>"
    )
    logger.info(f"Admin {message.from_user.id} created promo: {code}")


@router.message(Command("promos"))
@admin_only
async def cmd_promos(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        promos = await PromoRepository(session).list_all()

    if not promos:
        await message.answer("Промокодов нет. Создай: /addpromo")
        return

    lines = ["🎫 <b>Все промокоды</b>\n"]
    for p in promos:
        status = "🟢" if p.is_active else "🔴"
        uses = f"{p.uses_count}/{p.max_uses}" if p.max_uses > 0 else f"{p.uses_count}/∞"

        if p.promo_type == PromoType.PERCENT:
            disc = f"-{p.value:.0f}%"
        elif p.promo_type == PromoType.FIXED_RUB:
            disc = f"-{p.value:.0f}₽"
        else:
            disc = f"-{p.value}$"

        exp = p.expires_at.strftime("%d.%m.%y") if p.expires_at else "∞"
        lines.append(
            f"{status} <code>{p.code}</code> | {disc} | {uses} | до {exp}"
        )

    await message.answer("\n".join(lines))


@router.message(Command("delpromo"))
@admin_only
async def cmd_delpromo(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /delpromo <CODE>")
        return

    code = parts[1].upper()
    async with AsyncSessionLocal() as session:
        ok = await PromoRepository(session).deactivate(code)

    if ok:
        await message.answer(f"✅ Промокод <code>{code}</code> деактивирован")
    else:
        await message.answer(f"❌ Промокод <code>{code}</code> не найден")
