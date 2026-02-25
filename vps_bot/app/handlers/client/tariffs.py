from aiogram import Router, F
from aiogram.types import CallbackQuery
from app.core.config import TARIFFS
from app.utils.keyboards import tariffs_kb, tariff_detail_kb, payment_method_kb

router = Router(name="tariffs")


@router.callback_query(F.data == "tariffs")
async def cb_tariffs(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "📦 <b>Тарифы VPS</b>\n\n"
        "Все серверы на <b>Hetzner</b> (Германия)\n"
        "🐧 Ubuntu 22.04 • 🌐 1 Гбит/с порт\n\n"
        "Выбери подходящий план:",
        reply_markup=tariffs_kb(),
    )


@router.callback_query(F.data.startswith("tariff:"))
async def cb_tariff_detail(call: CallbackQuery) -> None:
    tariff_id = call.data.split(":", 1)[1]
    t = TARIFFS.get(tariff_id)
    if not t:
        await call.answer("Тариф не найден", show_alert=True)
        return

    text = (
        f"{t['name']}\n\n"
        f"📋 {t['description']}\n\n"
        f"💰 Стоимость:\n"
        f"   💳 Карта РФ: <b>{t['price_rub']} ₽/мес</b>\n"
        f"   💰 USDT: <b>{t['price_usdt']}/мес</b>\n\n"
        f"🌍 Локация: Германия\n"
        f"⚡ Создание: ~1 минута автоматически"
    )
    await call.message.edit_text(text, reply_markup=tariff_detail_kb(tariff_id))


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(call: CallbackQuery) -> None:
    tariff_id = call.data.split(":", 1)[1]
    t = TARIFFS.get(tariff_id)
    if not t:
        await call.answer("Тариф не найден", show_alert=True)
        return

    await call.message.edit_text(
        f"💳 <b>Выбери способ оплаты</b>\n\n"
        f"Тариф: <b>{t['name']}</b>\n\n"
        f"• Карта РФ (ЮKassa): <b>{t['price_rub']} ₽</b>\n"
        f"• Крипта USDT (CryptoBot): <b>{t['price_usdt']}</b>",
        reply_markup=payment_method_kb(tariff_id),
    )
