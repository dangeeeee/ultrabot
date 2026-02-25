"""
Реферальная программа для пользователей.

/start?ref=<telegram_id>  — регистрация с реферальным кодом
Команда /ref — показ реферальной ссылки и статистики
"""
from __future__ import annotations
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.referral import ReferralRepository

logger = logging.getLogger(__name__)
router = Router(name="referral")


def referral_kb(bot_username: str, telegram_id: int) -> InlineKeyboardMarkup:
    ref_link = f"https://t.me/{bot_username}?start=ref{telegram_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Моя реферальная ссылка", url=ref_link)],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
    ])


@router.message(CommandStart(deep_link=True))
async def cmd_start_ref(message: Message, command: CommandObject) -> None:
    """Обработка /start ref<id>"""
    if not settings.REFERRAL_ENABLED:
        return

    param = command.args or ""
    if not param.startswith("ref"):
        return

    try:
        referrer_id = int(param[3:])
    except ValueError:
        return

    async with AsyncSessionLocal() as session:
        repo = ReferralRepository(session)
        added = await repo.register_referral(referrer_id, message.from_user.id)

    if added:
        logger.info(f"New referral: {referrer_id} → {message.from_user.id}")
        # Уведомляем реферера
        try:
            await message.bot.send_message(
                referrer_id,
                f"🎉 По твоей ссылке зарегистрировался новый пользователь!\n"
                f"Когда он сделает первую покупку, ты получишь бонус "
                f"<b>{settings.REFERRAL_BONUS_RUB} ₽</b> / "
                f"<b>{settings.REFERRAL_BONUS_USDT} USDT</b>.",
            )
        except Exception:
            pass


@router.message(F.text == "/ref")
@router.callback_query(F.data == "referral")
async def show_referral(event: Message | CallbackQuery) -> None:
    if not settings.REFERRAL_ENABLED:
        if isinstance(event, CallbackQuery):
            await event.answer("Реферальная программа отключена.", show_alert=True)
        return

    user_id = event.from_user.id
    me = await event.bot.get_me()

    async with AsyncSessionLocal() as session:
        repo = ReferralRepository(session)
        total = await repo.count_referrals(user_id)
        paid = await repo.count_paid_referrals(user_id)
        balance = await repo.get_or_create_balance(user_id)

    ref_link = f"https://t.me/{me.username}?start=ref{user_id}"
    text = (
        f"👥 <b>Реферальная программа</b>\n\n"
        f"За каждого друга который купит VPS — получаешь бонус:\n"
        f"  💳 <b>{settings.REFERRAL_BONUS_RUB} ₽</b> или <b>{settings.REFERRAL_BONUS_USDT} USDT</b>\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📊 Твоя статистика:\n"
        f"  👤 Приглашено: <b>{total}</b>\n"
        f"  ✅ Купили VPS: <b>{paid}</b>\n"
        f"  💰 Бонусный баланс: <b>{float(balance.balance_rub):.2f} ₽</b>\n\n"
        f"🔗 Твоя ссылка:\n"
        f"<code>{ref_link}</code>"
    )

    kb = referral_kb(me.username, user_id)
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb)
    else:
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()
