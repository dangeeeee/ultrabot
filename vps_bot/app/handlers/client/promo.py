"""
Обработчик ввода промокода в процессе покупки.

Флоу:
  buy:tariff → кнопка "У меня есть промокод" → FSM promo_input
  → пользователь вводит код → валидация → применение скидки
  → показ обновлённой цены → выбор способа оплаты
"""
from __future__ import annotations
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.core.config import TARIFFS
from app.core.database import AsyncSessionLocal
from app.services.promo import PromoRepository

logger = logging.getLogger(__name__)
router = Router(name="promo")


class PromoFSM(StatesGroup):
    waiting_code = State()


def payment_with_promo_kb(tariff_id: str, renew_vps_id: int | None = None) -> InlineKeyboardMarkup:
    sfx = f":{renew_vps_id}" if renew_vps_id else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Карта РФ (ЮKassa)", callback_data=f"pay:yukassa:{tariff_id}{sfx}")],
        [InlineKeyboardButton(text="💰 Крипта USDT (CryptoBot)", callback_data=f"pay:crypto:{tariff_id}{sfx}")],
        [InlineKeyboardButton(text="🎫 У меня есть промокод", callback_data=f"enter_promo:{tariff_id}{sfx}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"tariff:{tariff_id}")],
    ])


def payment_after_promo_kb(
    tariff_id: str,
    promo_code: str,
    renew_vps_id: int | None = None,
) -> InlineKeyboardMarkup:
    sfx = f":{renew_vps_id}" if renew_vps_id else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💳 Карта РФ",
            callback_data=f"pay:yukassa:{tariff_id}{sfx}:{promo_code}"
        )],
        [InlineKeyboardButton(
            text="💰 Крипта USDT",
            callback_data=f"pay:crypto:{tariff_id}{sfx}:{promo_code}"
        )],
        [InlineKeyboardButton(text="🔄 Другой промокод", callback_data=f"enter_promo:{tariff_id}{sfx}")],
        [InlineKeyboardButton(text="✖️ Без промокода", callback_data=f"buy:{tariff_id}")],
    ])


@router.callback_query(F.data.startswith("enter_promo:"))
async def cb_enter_promo(call: CallbackQuery, state: FSMContext) -> None:
    parts = call.data.split(":", 1)
    rest = parts[1]  # tariff_id[:renew_vps_id]
    await state.set_state(PromoFSM.waiting_code)
    await state.update_data(promo_context=rest)
    await call.message.answer(
        "🎫 <b>Введи промокод</b>\n\n"
        "Напиши код и отправь сообщение.\n"
        "<i>Отмена: /cancel</i>"
    )
    await call.answer()


@router.message(PromoFSM.waiting_code)
async def handle_promo_code(message: Message, state: FSMContext) -> None:
    code = message.text.strip().upper()
    data = await state.get_data()
    context = data.get("promo_context", "")

    parts = context.split(":")
    tariff_id = parts[0]
    renew_vps_id = int(parts[1]) if len(parts) > 1 else None

    t = TARIFFS.get(tariff_id)
    if not t:
        await state.clear()
        return

    async with AsyncSessionLocal() as session:
        repo = PromoRepository(session)
        try:
            promo, discount, currency = await repo.validate(code, message.from_user.id, tariff_id)
        except ValueError as e:
            await message.answer(
                f"{e}\n\nПопробуй другой код или продолжи без промокода.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ К оплате", callback_data=f"buy:{tariff_id}")]
                ])
            )
            await state.clear()
            return

    await state.clear()

    # Показываем итоговую цену со скидкой
    new_price_rub = max(0, t["price_rub"] - (discount if currency == "RUB" else 0))
    new_price_usdt = max(0, t["price_usdt"] - (discount if currency == "USDT" else 0))

    from app.services.promo import PromoType
    if promo.promo_type == PromoType.PERCENT:
        new_price_rub = t["price_rub"] * (1 - float(promo.value) / 100)
        new_price_usdt = t["price_usdt"] * (1 - float(promo.value) / 100)
        discount_str = f"-{promo.value:.0f}%"
    elif promo.promo_type == PromoType.FIXED_RUB:
        new_price_rub = max(0, t["price_rub"] - float(promo.value))
        discount_str = f"-{promo.value:.0f} ₽"
    else:
        new_price_usdt = max(0, t["price_usdt"] - float(promo.value))
        discount_str = f"-{promo.value} USDT"

    await message.answer(
        f"✅ <b>Промокод <code>{code}</code> применён!</b>\n\n"
        f"📦 Тариф: <b>{t['name']}</b>\n"
        f"🎫 Скидка: <b>{discount_str}</b>\n\n"
        f"💰 Итого к оплате:\n"
        f"  💳 Карта РФ: <b>{new_price_rub:.0f} ₽</b> "
        f"<s>{t['price_rub']} ₽</s>\n"
        f"  💰 USDT: <b>{new_price_usdt:.2f}</b> "
        f"<s>{t['price_usdt']}</s>\n\n"
        f"Выбери способ оплаты:",
        reply_markup=payment_after_promo_kb(tariff_id, code, renew_vps_id),
    )
