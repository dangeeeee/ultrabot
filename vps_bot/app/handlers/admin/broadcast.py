"""
Рассылка пользователям.

FSM:
  adm:broadcast → (ввод текста) → предпросмотр → подтверждение → рассылка

Статус обновляется каждые 50 сообщений.
Уважает лимиты Telegram: 25 msg/сек.
"""
from __future__ import annotations
import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.core.database import AsyncSessionLocal
from app.core.states import BroadcastFSM
from app.repositories.user import UserRepository
from app.utils.admin import AdminFilter
from app.utils.keyboards import back_kb, adm_confirm_kb

logger = logging.getLogger(__name__)

router = Router(name="admin_broadcast")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

_RATE_CHUNK = 25    # сообщений перед паузой
_RATE_SLEEP = 1.0   # секунд паузы


@router.callback_query(F.data == "adm:broadcast")
async def cb_broadcast_start(call: CallbackQuery, state: FSMContext) -> None:
    """Открыть форму рассылки."""
    await state.set_state(BroadcastFSM.waiting_text)
    await call.message.edit_text(
        "📢 <b>Рассылка пользователям</b>\n\n"
        "Напиши текст сообщения.\n"
        "Поддерживается HTML: <b>жирный</b>, <i>курсив</i>, <code>код</code>, "
        "<a href='https://example.com'>ссылка</a>\n\n"
        "<i>Отмена — /cancel</i>",
        reply_markup=back_kb("adm:home"),
    )
    await call.answer()


@router.message(BroadcastFSM.waiting_text)
async def msg_broadcast_preview(message: Message, state: FSMContext) -> None:
    """Показать предпросмотр сообщения перед отправкой."""
    await state.update_data(broadcast_text=message.html_text)

    async with AsyncSessionLocal() as session:
        total = await UserRepository(session).count()

    await message.answer(
        f"📋 <b>Предпросмотр рассылки</b>\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{message.html_text}\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Получателей: <b>{total}</b>\n\n"
        "Подтвердить отправку?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить",   callback_data="adm:broadcast:confirm")],
            [InlineKeyboardButton(text="✏️ Изменить",    callback_data="adm:broadcast:edit")],
            [InlineKeyboardButton(text="❌ Отменить",    callback_data="adm:broadcast:cancel")],
        ]),
    )


@router.callback_query(F.data == "adm:broadcast:edit")
async def cb_broadcast_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BroadcastFSM.waiting_text)
    await call.message.edit_text(
        "✏️ Введи новый текст рассылки:\n\n<i>Отмена — /cancel</i>",
        reply_markup=back_kb("adm:home"),
    )
    await call.answer()


@router.callback_query(F.data == "adm:broadcast:cancel")
async def cb_broadcast_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text(
        "❌ Рассылка отменена.",
        reply_markup=back_kb("adm:home"),
    )
    await call.answer()


@router.callback_query(F.data == "adm:broadcast:confirm")
async def cb_broadcast_confirm(call: CallbackQuery, state: FSMContext) -> None:
    """Запустить рассылку."""
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    await state.clear()

    if not text:
        await call.answer("Текст пустой", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        ids = await UserRepository(session).get_all_ids()

    total = len(ids)
    status_msg = await call.message.edit_text(
        f"📢 <b>Рассылка запущена...</b>\n\n"
        f"👥 Получателей: {total}\n"
        f"⏳ Отправляю..."
    )

    sent = failed = 0
    for i, uid in enumerate(ids):
        try:
            await call.bot.send_message(uid, f"📢 {text}")
            sent += 1
        except Exception:
            failed += 1

        # Обновляем статус каждые 50 сообщений
        if (i + 1) % 50 == 0:
            pct = (i + 1) / total * 100
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            try:
                await status_msg.edit_text(
                    f"📢 <b>Рассылка...</b>\n\n"
                    f"{bar} {pct:.0f}%\n"
                    f"Прогресс: {i + 1}/{total}\n"
                    f"✅ Отправлено: {sent}  ❌ Ошибок: {failed}"
                )
            except Exception:
                pass

        # Rate limiting
        if (i + 1) % _RATE_CHUNK == 0:
            await asyncio.sleep(_RATE_SLEEP)

    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📊 Итоги:\n"
        f"  👥 Всего: {total}\n"
        f"  ✅ Доставлено: {sent}\n"
        f"  ❌ Заблокировали бота: {failed}",
        reply_markup=back_kb("adm:home"),
    )
    logger.info(f"Broadcast done: {sent}/{total} delivered by admin {call.from_user.id}")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current:
        await state.clear()
        await message.answer("❌ Действие отменено.", reply_markup=back_kb("adm:home"))
    else:
        await message.answer("Нечего отменять.")
