"""
Поиск пользователей через FSM.
Обрабатывает состояния adm_find_user и adm_send_msg из panel.py.
"""
from __future__ import annotations
import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from app.core.database import AsyncSessionLocal
from app.repositories.user import UserRepository
from app.utils.admin import AdminFilter
from app.utils.keyboards import adm_user_profile_kb, back_kb

logger = logging.getLogger(__name__)

router = Router(name="admin_users_fsm")
router.message.filter(AdminFilter())


@router.message(F.text, F.func(lambda msg: True))
async def handle_admin_text(message: Message, state: FSMContext) -> None:
    """Маршрутизация текстового ввода в зависимости от состояния FSM."""
    current = await state.get_state()

    if current == "adm_find_user":
        await _do_find_user(message, state)
    elif current == "adm_find_vps":
        await _do_find_vps(message, state)
    elif current == "adm_send_msg":
        await _do_send_msg(message, state)


async def _do_find_user(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    by_username = data.get("find_by_username", False)
    await state.clear()

    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        if by_username:
            uname = message.text.lstrip("@").strip()
            user = await repo.get_by_username(uname)
        else:
            try:
                tid = int(message.text.strip())
                user = await repo.get_by_telegram_id(tid)
            except ValueError:
                await message.answer("❌ ID должен быть числом.", reply_markup=back_kb("adm:users"))
                return

        if not user:
            await message.answer("❌ Пользователь не найден.", reply_markup=back_kb("adm:users"))
            return

        from app.repositories.user import PaymentRepository
        from app.repositories.vps import VpsRepository
        pay_count = await PaymentRepository(session).count_paid_by_user(user.telegram_id)
        total_spent = await PaymentRepository(session).total_by_user(user.telegram_id)
        vps_list = await VpsRepository(session).get_user_vps(user.telegram_id)

    active_vps = sum(1 for v in vps_list if v.status.value == "active")
    ban_icon = "🚫 Заблокирован" if user.is_banned else "✅ Активен"

    text = (
        f"👤 <b>Пользователь найден</b>\n\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"📛 Имя: {user.full_name or '—'}\n"
        f"🔗 Username: @{user.username or '—'}\n"
        f"📋 Статус: {ban_icon}\n"
        f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"💳 Оплат: <b>{pay_count}</b>  |  💰 Потрачено: <b>{total_spent:.2f}</b>\n"
        f"🖥️ Серверов: <b>{len(vps_list)}</b> (активных: {active_vps})"
    )
    await message.answer(text, reply_markup=adm_user_profile_kb(user.telegram_id, user.is_banned))


async def _do_find_vps(message: Message, state: FSMContext) -> None:
    ip = message.text.strip()
    await state.clear()

    from app.repositories.vps import VpsRepository
    from app.utils.keyboards import adm_vps_card_kb
    async with AsyncSessionLocal() as session:
        vps = await VpsRepository(session).get_by_ip(ip)

    if not vps:
        await message.answer(f"❌ VPS с IP <code>{ip}</code> не найден.", reply_markup=back_kb("adm:vps"))
        return

    await message.answer(
        f"✅ Найден VPS #{vps.id}",
        reply_markup=adm_vps_card_kb(vps.id, vps.telegram_id),
    )


async def _do_send_msg(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    target_id = data.get("target_user_id")
    await state.clear()

    if not target_id:
        await message.answer("❌ Потеряли ID пользователя. Начни заново.")
        return

    try:
        await message.bot.send_message(target_id, f"✉️ <b>Сообщение от администратора</b>\n\n{message.html_text}")
        await message.answer(
            f"✅ Сообщение отправлено пользователю <code>{target_id}</code>",
            reply_markup=back_kb(f"adm:user:{target_id}"),
        )
        logger.info(f"Admin {message.from_user.id} sent message to {target_id}")
    except Exception as e:
        await message.answer(
            f"❌ Не удалось отправить: {e}",
            reply_markup=back_kb(f"adm:user:{target_id}"),
        )
