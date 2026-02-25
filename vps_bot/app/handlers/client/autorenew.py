from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from app.core.redis import get_redis

router = Router(name="autorenew")


def autorenew_kb(enabled: bool) -> InlineKeyboardMarkup:
    if enabled:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔴 Выключить", callback_data="autorenew:off")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Включить", callback_data="autorenew:on")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
        ])


async def _show_autorenew(event: Message | CallbackQuery) -> None:
    user_id = event.from_user.id
    redis = await get_redis()
    enabled = (await redis.get(f"autorenew:{user_id}")) == "1"
    status = "🟢 Включено" if enabled else "🔴 Выключено"

    text = (
        f"🔄 <b>Автопродление VPS</b>\n\n"
        f"Статус: <b>{status}</b>\n\n"
        f"При включении — за 24 часа до истечения VPS автоматически "
        f"продлевается с твоего <b>бонусного баланса</b>.\n\n"
        f"Баланс пополняется через реферальную программу: /ref"
    )
    kb = autorenew_kb(enabled)

    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb)
    else:
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()


@router.message(Command("autorenew"))
async def cmd_autorenew(message: Message) -> None:
    await _show_autorenew(message)


@router.callback_query(F.data == "autorenew_settings")
async def cb_autorenew(call: CallbackQuery) -> None:
    await _show_autorenew(call)


@router.callback_query(F.data.startswith("autorenew:"))
async def cb_toggle_autorenew(call: CallbackQuery) -> None:
    action = call.data.split(":")[1]
    redis = await get_redis()
    key = f"autorenew:{call.from_user.id}"

    if action == "on":
        await redis.set(key, "1")
        await call.answer("✅ Автопродление включено", show_alert=True)
    else:
        await redis.set(key, "0")
        await call.answer("❌ Автопродление выключено", show_alert=True)

    await _show_autorenew(call)
