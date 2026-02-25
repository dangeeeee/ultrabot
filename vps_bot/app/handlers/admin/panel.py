"""
Главная инлайн-панель администратора.

Навигация полностью через callback_data — никаких команд кроме /admin.

Дерево экранов:
  /admin → adm:home
    adm:stats → adm:stats:7d / adm:stats:30d / adm:stats:tariffs
    adm:users → adm:users:recent / adm:users:banned / adm:users:find
              → adm:user:<id> → adm:user:ban / adm:user:vps / adm:user:msg
    adm:vps   → adm:vps:filter:* / adm:vps:find
              → adm:vps:<id> → adm:vps:reboot / adm:vps:delete / adm:vps:ping
    adm:broadcast → (FSM) → broadcast.py
    adm:settings → adm:settings:proxmox / adm:settings:ippool / adm:settings:test_notify
"""
from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core.config import settings, TARIFFS
from app.core.database import AsyncSessionLocal
from app.core.states import BroadcastFSM, AdminFSM
from app.repositories.user import UserRepository, PaymentRepository
from app.repositories.vps import VpsRepository
from app.services.proxmox import proxmox_service
from app.services.stats import StatsService, format_stats_text
from app.utils.admin import AdminFilter
from app.utils.keyboards import (
    adm_home_kb, adm_stats_kb, adm_users_kb, adm_user_profile_kb,
    adm_user_vps_kb, adm_vps_kb, adm_vps_card_kb, adm_settings_kb,
    adm_confirm_kb, back_kb,
)

logger = logging.getLogger(__name__)

# Применяем AdminFilter ко всему роутеру — не-админы сюда не попадут
router = Router(name="admin_panel")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

PAGE_SIZE = 8  # записей на страницу пагинации


# ═══════════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ═══════════════════════════════════════════════════════════════

@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Команда /admin — открывает главное меню панели."""
    await _render_home(message)


@router.callback_query(F.data == "adm:home")
async def cb_adm_home(call: CallbackQuery) -> None:
    await call.message.edit_text(
        _home_text(),
        reply_markup=adm_home_kb(),
    )
    await call.answer()


def _home_text() -> str:
    return (
        "🔧 <b>Панель администратора</b>\n\n"
        "Выбери раздел:"
    )


async def _render_home(message: Message) -> None:
    await message.answer(_home_text(), reply_markup=adm_home_kb())


# ═══════════════════════════════════════════════════════════════
# 📊 СТАТИСТИКА
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:stats")
async def cb_adm_stats(call: CallbackQuery) -> None:
    """Главный экран статистики с детальными данными."""
    await call.answer("⏳ Загружаю...")

    async with AsyncSessionLocal() as session:
        stats = await StatsService(session).get_full_stats()

    # Пробуем получить статус Proxmox
    try:
        node = await proxmox_service.node_status()
        proxmox_info = (
            f"\n\n🖥️ <b>Proxmox:</b> CPU {node['cpu_pct']}% · "
            f"RAM {node['mem_used_gb']}/{node['mem_total_gb']} GB"
        )
    except Exception:
        proxmox_info = "\n\n⚠️ Proxmox недоступен"

    text = format_stats_text(stats) + proxmox_info

    await call.message.edit_text(text, reply_markup=adm_stats_kb())


@router.callback_query(F.data.in_({"adm:stats:7d", "adm:stats:30d"}))
async def cb_adm_stats_revenue(call: CallbackQuery) -> None:
    """Детальная разбивка выручки по дням."""
    days = 7 if call.data == "adm:stats:7d" else 30
    await call.answer("⏳")

    async with AsyncSessionLocal() as session:
        daily = await StatsService(session)._get_daily_revenue(days)

    if not daily:
        await call.answer("Нет данных за этот период", show_alert=True)
        return

    lines = [f"📈 <b>Выручка по дням (последние {days}д.)</b>\n"]
    total = 0.0
    for d in daily:
        day_str = d["date"][5:]  # MM-DD
        lines.append(f"  {day_str}   <b>{d['total']:>8.2f}</b>  ({d['count']} оплат)")
        total += d["total"]
    lines.append(f"\n💰 <b>Итого: {total:.2f}</b>")

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=back_kb("adm:stats"),
    )


@router.callback_query(F.data == "adm:stats:tariffs")
async def cb_adm_stats_tariffs(call: CallbackQuery) -> None:
    """Топ тарифов по количеству продаж."""
    await call.answer("⏳")

    async with AsyncSessionLocal() as session:
        tariff_stats = await StatsService(session)._get_tariff_stats()

    if not tariff_stats:
        await call.answer("Нет данных", show_alert=True)
        return

    total = sum(t["count"] for t in tariff_stats)
    lines = ["🏆 <b>Популярность тарифов</b>\n"]
    for i, t in enumerate(tariff_stats, 1):
        pct = t["count"] / total * 100 if total else 0
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        lines.append(f"  {i}. {t['name']}\n     {bar} {pct:.0f}%  ({t['count']} шт.)")

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=back_kb("adm:stats"),
    )


# ═══════════════════════════════════════════════════════════════
# 👥 ПОЛЬЗОВАТЕЛИ
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.in_({"adm:users", "adm:users:page:0"}))
async def cb_adm_users(call: CallbackQuery) -> None:
    """Главный экран раздела пользователей."""
    async with AsyncSessionLocal() as session:
        total = await UserRepository(session).count()

    text = (
        f"👥 <b>Пользователи</b>\n\n"
        f"Всего зарегистрировано: <b>{total}</b>\n\n"
        "Выбери действие:"
    )
    await call.message.edit_text(text, reply_markup=adm_users_kb())
    await call.answer()


@router.callback_query(F.data == "adm:users:recent")
async def cb_adm_users_recent(call: CallbackQuery) -> None:
    """Последние зарегистрированные пользователи."""
    await call.answer("⏳")

    async with AsyncSessionLocal() as session:
        users = await UserRepository(session).get_recent(10)

    if not users:
        await call.answer("Нет пользователей", show_alert=True)
        return

    lines = ["👥 <b>Последние 10 пользователей</b>\n"]
    for u in users:
        ban = " 🚫" if u.is_banned else ""
        uname = f"@{u.username}" if u.username else "—"
        lines.append(
            f"  <code>{u.telegram_id}</code>  {uname}  {u.full_name or '—'}{ban}\n"
            f"  <i>{u.created_at.strftime('%d.%m.%Y %H:%M')}</i>"
        )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    # Кнопки на каждого пользователя
    rows = [
        [InlineKeyboardButton(
            text=f"{'🚫 ' if u.is_banned else ''}{u.full_name or u.telegram_id}",
            callback_data=f"adm:user:{u.telegram_id}",
        )]
        for u in users
    ]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm:users")])

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "adm:users:banned")
async def cb_adm_users_banned(call: CallbackQuery) -> None:
    """Список заблокированных пользователей."""
    await call.answer("⏳")

    async with AsyncSessionLocal() as session:
        users = await UserRepository(session).get_banned()

    if not users:
        await call.message.edit_text(
            "🚫 <b>Забаненные пользователи</b>\n\nСписок пуст.",
            reply_markup=back_kb("adm:users"),
        )
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rows = [
        [InlineKeyboardButton(
            text=f"🚫 {u.full_name or u.telegram_id} (@{u.username or '—'})",
            callback_data=f"adm:user:{u.telegram_id}",
        )]
        for u in users
    ]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm:users")])

    await call.message.edit_text(
        f"🚫 <b>Забаненные ({len(users)})</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.in_({"adm:users:find", "adm:users:find_username"}))
async def cb_adm_users_find(call: CallbackQuery, state: FSMContext) -> None:
    """Начало поиска пользователя."""
    by_username = call.data == "adm:users:find_username"
    if by_username:
        await state.set_state(AdminFSM.find_user_by_username)
        hint = "username (без @)"
    else:
        await state.set_state(AdminFSM.find_user_by_id)
        hint = "Telegram ID (числом)"

    await call.message.edit_text(
        f"🔍 <b>Поиск пользователя</b>\n\n"
        f"Введи {hint}:\n\n"
        f"<i>Отмена — /cancel</i>",
        reply_markup=back_kb("adm:users"),
    )
    await call.answer()


@router.message(AdminFSM.find_user_by_id)
async def fsm_find_user_by_id(message: Message, state: FSMContext) -> None:
    """FSM: получаем Telegram ID для поиска пользователя."""
    await state.clear()
    text = message.text.strip() if message.text else ""

    try:
        tid = int(text)
    except ValueError:
        await message.answer(
            "❌ Telegram ID должен быть числом. Попробуй снова:",
            reply_markup=back_kb("adm:users"),
        )
        return

    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(tid)

    if not user:
        await message.answer(
            f"❌ Пользователь с ID <code>{tid}</code> не найден.",
            reply_markup=back_kb("adm:users"),
        )
        return

    async with AsyncSessionLocal() as session:
        pay_count = await PaymentRepository(session).count_paid_by_user(tid)
        total_spent = await PaymentRepository(session).total_by_user(tid)
        vps_list = await VpsRepository(session).get_user_vps(tid)

    active_vps = sum(1 for v in vps_list if v.status.value == "active")
    ban_icon = "🚫 Заблокирован" if user.is_banned else "✅ Активен"

    text = (
        f"👤 <b>Пользователь (результат поиска)</b>\n\n"
        f"🆔 ID: <code>{tid}</code>\n"
        f"📛 Имя: {user.full_name or '—'}\n"
        f"🔗 Username: @{user.username or '—'}\n"
        f"📋 Статус: {ban_icon}\n"
        f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"💳 Оплат: <b>{pay_count}</b>  |  💰 Потрачено: <b>{total_spent:.2f}</b>\n"
        f"🖥️ Серверов: <b>{len(vps_list)}</b> (активных: {active_vps})"
    )
    await message.answer(text, reply_markup=adm_user_profile_kb(tid, user.is_banned))


@router.message(AdminFSM.find_user_by_username)
async def fsm_find_user_by_username(message: Message, state: FSMContext) -> None:
    """FSM: получаем username для поиска пользователя."""
    await state.clear()
    username = (message.text or "").strip().lstrip("@")
    if not username:
        await message.answer("❌ Введи username", reply_markup=back_kb("adm:users"))
        return

    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_username(username)

    if not user:
        await message.answer(
            f"❌ Пользователь @{username} не найден.",
            reply_markup=back_kb("adm:users"),
        )
        return

    # Используем существующий рендер профиля
    async with AsyncSessionLocal() as session:
        pay_count = await PaymentRepository(session).count_paid_by_user(user.telegram_id)
        total_spent = await PaymentRepository(session).total_by_user(user.telegram_id)
        vps_list = await VpsRepository(session).get_user_vps(user.telegram_id)

    active_vps = sum(1 for v in vps_list if v.status.value == "active")
    ban_icon = "🚫 Заблокирован" if user.is_banned else "✅ Активен"

    text = (
        f"👤 <b>Пользователь (результат поиска)</b>\n\n"
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


@router.message(AdminFSM.find_vps_by_ip)
async def fsm_find_vps_by_ip(message: Message, state: FSMContext) -> None:
    """FSM: поиск VPS по IP адресу."""
    await state.clear()
    ip = (message.text or "").strip()
    if not ip:
        await message.answer("❌ Введи IP адрес", reply_markup=back_kb("adm:vps"))
        return

    async with AsyncSessionLocal() as session:
        vps = await VpsRepository(session).get_by_ip(ip)

    if not vps:
        await message.answer(
            f"❌ VPS с IP <code>{ip}</code> не найден.",
            reply_markup=back_kb("adm:vps"),
        )
        return

    await message.answer(f"✅ Найден VPS #{vps.id}", reply_markup=adm_vps_card_kb(vps.id, vps.telegram_id))


@router.message(AdminFSM.send_message_to_user)
async def fsm_send_message_to_user(message: Message, state: FSMContext) -> None:
    """FSM: отправить личное сообщение пользователю."""
    data = await state.get_data()
    await state.clear()
    target_id = data.get("target_user_id")
    if not target_id:
        await message.answer("❌ Потерян контекст. Начни заново.")
        return

    try:
        await message.bot.send_message(
            target_id,
            f"📩 <b>Сообщение от администратора:</b>\n\n{message.html_text}",
        )
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


@router.callback_query(F.data.startswith("adm:user:") & ~F.data.contains(":ban:")
                       & ~F.data.contains(":unban:") & ~F.data.contains(":vps:")
                       & ~F.data.contains(":msg:"))
async def cb_adm_user_profile(call: CallbackQuery) -> None:
    """Профиль конкретного пользователя."""
    try:
        tid = int(call.data.split(":")[2])
    except (IndexError, ValueError):
        await call.answer("Неверный формат", show_alert=True)
        return

    await call.answer("⏳")

    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(tid)
        if not user:
            await call.answer("Пользователь не найден", show_alert=True)
            return
        pay_count = await PaymentRepository(session).count_paid_by_user(tid)
        total_spent = await PaymentRepository(session).total_by_user(tid)
        vps_list = await VpsRepository(session).get_user_vps(tid)

    active_vps = sum(1 for v in vps_list if v.status.value == "active")
    ban_icon = "🚫 Заблокирован" if user.is_banned else "✅ Активен"

    text = (
        f"👤 <b>Пользователь</b>\n\n"
        f"🆔 ID: <code>{tid}</code>\n"
        f"📛 Имя: {user.full_name or '—'}\n"
        f"🔗 Username: @{user.username or '—'}\n"
        f"📋 Статус: {ban_icon}\n"
        f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"💳 Оплат: <b>{pay_count}</b>  |  "
        f"💰 Потрачено: <b>{total_spent:.2f}</b>\n"
        f"🖥️ Серверов: <b>{len(vps_list)}</b> (активных: {active_vps})"
    )

    await call.message.edit_text(
        text,
        reply_markup=adm_user_profile_kb(tid, user.is_banned),
    )


@router.callback_query(F.data.startswith("adm:user:ban:"))
async def cb_adm_user_ban(call: CallbackQuery) -> None:
    """Заблокировать пользователя с подтверждением."""
    tid = int(call.data.split(":")[3])
    await call.message.edit_text(
        f"🚫 <b>Подтверждение бана</b>\n\n"
        f"Заблокировать пользователя <code>{tid}</code>?\n"
        f"Он больше не сможет пользоваться ботом.",
        reply_markup=adm_confirm_kb(
            yes_cb=f"adm:user:ban:confirm:{tid}",
            no_cb=f"adm:user:{tid}",
        ),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:user:ban:confirm:"))
async def cb_adm_user_ban_confirm(call: CallbackQuery) -> None:
    tid = int(call.data.split(":")[4])

    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(tid)
        if not user:
            await call.answer("Пользователь не найден", show_alert=True)
            return
        await UserRepository(session).set_banned(tid, True)

    try:
        await call.bot.send_message(tid, "🚫 Ваш аккаунт заблокирован администратором.")
    except Exception:
        pass

    logger.info(f"Admin {call.from_user.id} banned user {tid}")
    await call.answer(f"✅ {user.full_name or tid} заблокирован", show_alert=True)

    # Возвращаемся на профиль
    await _refresh_user_profile(call, tid)


@router.callback_query(F.data.startswith("adm:user:unban:"))
async def cb_adm_user_unban(call: CallbackQuery) -> None:
    tid = int(call.data.split(":")[3])

    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(tid)
        if not user:
            await call.answer("Пользователь не найден", show_alert=True)
            return
        await UserRepository(session).set_banned(tid, False)

    try:
        await call.bot.send_message(tid, "✅ Ваш аккаунт разблокирован.")
    except Exception:
        pass

    logger.info(f"Admin {call.from_user.id} unbanned user {tid}")
    await call.answer(f"✅ {user.full_name or tid} разблокирован", show_alert=True)
    await _refresh_user_profile(call, tid)


@router.callback_query(F.data.startswith("adm:user:msg:"))
async def cb_adm_user_msg(call: CallbackQuery, state: FSMContext) -> None:
    """Написать личное сообщение пользователю."""
    tid = int(call.data.split(":")[3])
    await state.set_state(AdminFSM.send_message_to_user)
    await state.update_data(target_user_id=tid)
    await call.message.edit_text(
        f"✉️ <b>Сообщение пользователю <code>{tid}</code></b>\n\n"
        "Напиши текст сообщения (поддерживается HTML).\n\n"
        "<i>Отмена — /cancel</i>",
        reply_markup=back_kb(f"adm:user:{tid}"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:user:vps:"))
async def cb_adm_user_vps(call: CallbackQuery) -> None:
    """Серверы пользователя из контекста админа."""
    tid = int(call.data.split(":")[3])
    await call.answer("⏳")

    async with AsyncSessionLocal() as session:
        vps_list = await VpsRepository(session).get_user_vps(tid)

    if not vps_list:
        await call.answer("У пользователя нет серверов", show_alert=True)
        return

    lines = [f"🖥️ <b>Серверы пользователя <code>{tid}</code></b>\n"]
    for v in vps_list:
        days = (v.expires_at - datetime.utcnow()).days
        icon = "🟢" if v.status.value == "active" and days > 0 else "🔴"
        t_name = TARIFFS.get(v.tariff, {}).get("name", v.tariff)
        lines.append(f"  {icon} #{v.id}  <code>{v.ip}</code>  {t_name}  {days}д.")

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=adm_user_vps_kb(vps_list, tid),
    )


async def _refresh_user_profile(call: CallbackQuery, tid: int) -> None:
    """Перерисовать профиль пользователя после изменения."""
    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(tid)
        if not user:
            return
        pay_count = await PaymentRepository(session).count_paid_by_user(tid)
        total_spent = await PaymentRepository(session).total_by_user(tid)
        vps_list = await VpsRepository(session).get_user_vps(tid)

    active_vps = sum(1 for v in vps_list if v.status.value == "active")
    ban_icon = "🚫 Заблокирован" if user.is_banned else "✅ Активен"

    text = (
        f"👤 <b>Пользователь</b>\n\n"
        f"🆔 ID: <code>{tid}</code>\n"
        f"📛 Имя: {user.full_name or '—'}\n"
        f"🔗 Username: @{user.username or '—'}\n"
        f"📋 Статус: {ban_icon}\n"
        f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"💳 Оплат: <b>{pay_count}</b>  |  💰 Потрачено: <b>{total_spent:.2f}</b>\n"
        f"🖥️ Серверов: <b>{len(vps_list)}</b> (активных: {active_vps})"
    )
    await call.message.edit_text(text, reply_markup=adm_user_profile_kb(tid, user.is_banned))


# ═══════════════════════════════════════════════════════════════
# 🖥️ СЕРВЕРЫ
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:vps")
async def cb_adm_vps(call: CallbackQuery) -> None:
    """Главный экран раздела серверов."""
    async with AsyncSessionLocal() as session:
        all_vps = await VpsRepository(session).get_all(limit=999)

    active = sum(1 for v in all_vps if v.status.value == "active")
    expired = sum(1 for v in all_vps
                  if v.status.value == "active" and (v.expires_at - datetime.utcnow()).days <= 0)

    text = (
        f"🖥️ <b>Серверы</b>\n\n"
        f"Всего: <b>{len(all_vps)}</b>  ·  "
        f"Активных: <b>{active}</b>  ·  "
        f"Просроченных: <b>{expired}</b>\n\n"
        "Выбери действие:"
    )
    await call.message.edit_text(text, reply_markup=adm_vps_kb())
    await call.answer()


@router.callback_query(F.data.startswith("adm:vps:filter:"))
async def cb_adm_vps_filter(call: CallbackQuery) -> None:
    """Фильтрованный список серверов."""
    flt = call.data.split(":")[3]  # active | expired
    await call.answer("⏳")

    async with AsyncSessionLocal() as session:
        vps_list = await VpsRepository(session).get_all(limit=50)

    now = datetime.utcnow()
    if flt == "active":
        filtered = [v for v in vps_list
                    if v.status.value == "active" and (v.expires_at - now).days > 0]
        title = "🟢 Активные серверы"
    else:
        filtered = [v for v in vps_list
                    if v.status.value != "active" or (v.expires_at - now).days <= 0]
        title = "🔴 Просроченные / удалённые"

    if not filtered:
        await call.answer("Нет серверов в этой категории", show_alert=True)
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rows = []
    for v in filtered[:20]:
        days = (v.expires_at - now).days
        icon = "🟢" if v.status.value == "active" and days > 0 else "🔴"
        t_name = TARIFFS.get(v.tariff, {}).get("name", v.tariff)
        rows.append([InlineKeyboardButton(
            text=f"{icon} #{v.id} {v.ip} · {t_name} · {days}д.",
            callback_data=f"adm:vps:{v.id}",
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm:vps")])

    await call.message.edit_text(
        f"{title} ({len(filtered)} шт.)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "adm:vps:find")
async def cb_adm_vps_find(call: CallbackQuery, state: FSMContext) -> None:
    """Поиск VPS по IP."""
    await state.set_state(AdminFSM.find_vps_by_ip)
    await call.message.edit_text(
        "🔍 <b>Поиск сервера по IP</b>\n\nВведи IP-адрес:\n\n<i>Отмена — /cancel</i>",
        reply_markup=back_kb("adm:vps"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:vps:") & F.data.regexp(r"adm:vps:\d+$"))
async def cb_adm_vps_card(call: CallbackQuery) -> None:
    """Карточка конкретного VPS."""
    vps_id = int(call.data.split(":")[2])
    await call.answer("⏳")

    async with AsyncSessionLocal() as session:
        vps = await VpsRepository(session).get_by_id(vps_id)

    if not vps:
        await call.answer("Сервер не найден", show_alert=True)
        return

    # Статус из Proxmox
    try:
        st = await proxmox_service.status_lxc(vps.vmid)
        prox_icon = "🟢" if st["running"] else "🔴"
        prox_line = (
            f"{prox_icon} {'Работает' if st['running'] else 'Остановлен'} · "
            f"CPU {st['cpu_pct']}% · "
            f"RAM {st['mem_used_mb']}/{st['mem_total_mb']}MB\n"
            f"⏱️ Аптайм: {st['uptime_sec'] // 3600}ч"
        )
    except Exception:
        prox_line = "⚠️ Proxmox недоступен"

    days = (vps.expires_at - datetime.utcnow()).days
    t = TARIFFS.get(vps.tariff, {})

    text = (
        f"🖥️ <b>Сервер #{vps_id}</b>\n\n"
        f"{prox_line}\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌐 IP: <code>{vps.ip}</code>\n"
        f"🔑 Пароль: <code>{vps.password}</code>\n"
        f"📦 Тариф: {t.get('name', vps.tariff)}\n"
        f"📅 Истекает: {vps.expires_at.strftime('%d.%m.%Y')} ({days}д.)\n"
        f"👤 Владелец: <code>{vps.telegram_id}</code>\n"
        f"🆔 VMID: {vps.vmid}"
    )

    await call.message.edit_text(text, reply_markup=adm_vps_card_kb(vps_id, vps.telegram_id))


@router.callback_query(F.data.startswith("adm:vps:reboot:"))
async def cb_adm_vps_reboot(call: CallbackQuery) -> None:
    vps_id = int(call.data.split(":")[3])
    await call.answer("⏳ Перезагружаю...")

    async with AsyncSessionLocal() as session:
        vps = await VpsRepository(session).get_by_id(vps_id)

    if not vps:
        await call.answer("Сервер не найден", show_alert=True)
        return

    try:
        await proxmox_service.reboot_lxc(vps.vmid)
        await call.answer("✅ Перезагружено", show_alert=True)
        logger.info(f"Admin {call.from_user.id} rebooted VPS #{vps_id}")
    except Exception as e:
        await call.answer(f"❌ Ошибка: {e}", show_alert=True)


@router.callback_query(F.data.startswith("adm:vps:ping:"))
async def cb_adm_vps_ping(call: CallbackQuery) -> None:
    vps_id = int(call.data.split(":")[3])
    await call.answer("⏳ Пингую...")

    async with AsyncSessionLocal() as session:
        vps = await VpsRepository(session).get_by_id(vps_id)

    if not vps:
        await call.answer("Сервер не найден", show_alert=True)
        return

    from app.handlers.client.ping import _ping_host, _format_ping_result
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    result = await _ping_host(vps.ip)
    text = _format_ping_result(vps.ip, result)

    await call.message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Повторить", callback_data=f"adm:vps:ping:{vps_id}")],
            [InlineKeyboardButton(text="◀️ К серверу", callback_data=f"adm:vps:{vps_id}")],
        ]),
    )


@router.callback_query(F.data.startswith("adm:vps:delete:"))
async def cb_adm_vps_delete_confirm(call: CallbackQuery) -> None:
    """Запрос подтверждения удаления VPS."""
    vps_id = int(call.data.split(":")[3])

    async with AsyncSessionLocal() as session:
        vps = await VpsRepository(session).get_by_id(vps_id)

    if not vps:
        await call.answer("Сервер не найден", show_alert=True)
        return

    await call.message.edit_text(
        f"🗑️ <b>Подтверждение удаления</b>\n\n"
        f"Удалить VPS #{vps_id}?\n"
        f"🌐 IP: <code>{vps.ip}</code>\n"
        f"👤 Владелец: <code>{vps.telegram_id}</code>\n\n"
        f"⚠️ Действие необратимо. Контейнер будет уничтожен в Proxmox.",
        reply_markup=adm_confirm_kb(
            yes_cb=f"adm:vps:delete:confirm:{vps_id}",
            no_cb=f"adm:vps:{vps_id}",
        ),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:vps:delete:confirm:"))
async def cb_adm_vps_delete_do(call: CallbackQuery) -> None:
    """Выполнить удаление VPS после подтверждения."""
    vps_id = int(call.data.split(":")[4])
    await call.answer("⏳ Удаляю...")

    async with AsyncSessionLocal() as session:
        repo = VpsRepository(session)
        vps = await repo.get_by_id(vps_id)
        if not vps:
            await call.answer("Сервер не найден", show_alert=True)
            return

        try:
            await proxmox_service.delete_lxc(vps.vmid)
            prox_ok = True
        except Exception as e:
            prox_ok = False
            logger.error(f"Proxmox delete error for vmid {vps.vmid}: {e}")

        await repo.mark_deleted(vps_id)
        await repo.release_ip(vps.ip)

    try:
        await call.bot.send_message(
            vps.telegram_id,
            f"⚠️ Твой сервер <code>{vps.ip}</code> удалён администратором.",
        )
    except Exception:
        pass

    proxmox_note = "✅" if prox_ok else "⚠️ (ошибка Proxmox, удалён из БД)"
    logger.info(f"Admin {call.from_user.id} deleted VPS #{vps_id}")

    await call.message.edit_text(
        f"✅ <b>VPS #{vps_id} удалён</b>\n\n"
        f"Proxmox: {proxmox_note}\n"
        f"Пользователь уведомлён.",
        reply_markup=back_kb("adm:vps"),
    )


# ═══════════════════════════════════════════════════════════════
# ⚙️ НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:settings")
async def cb_adm_settings(call: CallbackQuery) -> None:
    text = (
        f"⚙️ <b>Настройки и мониторинг</b>\n\n"
        f"Proxmox: <code>{settings.PROXMOX_HOST}</code>\n"
        f"Нода: <code>{settings.PROXMOX_NODE}</code>\n"
        f"Режим бота: <code>{settings.BOT_RUN_MODE}</code>"
    )
    await call.message.edit_text(text, reply_markup=adm_settings_kb())
    await call.answer()


@router.callback_query(F.data == "adm:settings:proxmox")
async def cb_adm_settings_proxmox(call: CallbackQuery) -> None:
    """Детальный статус Proxmox ноды."""
    await call.answer("⏳")
    try:
        st = await proxmox_service.node_status()
        cpu_bar = "█" * int(st["cpu_pct"] / 10) + "░" * (10 - int(st["cpu_pct"] / 10))
        mem_pct = st["mem_used_gb"] / st["mem_total_gb"] * 100 if st["mem_total_gb"] else 0
        mem_bar = "█" * int(mem_pct / 10) + "░" * (10 - int(mem_pct / 10))

        text = (
            f"🖥️ <b>Proxmox: {settings.PROXMOX_NODE}</b>\n\n"
            f"CPU: {cpu_bar} {st['cpu_pct']}%\n"
            f"RAM: {mem_bar} {st['mem_used_gb']}/{st['mem_total_gb']} GB\n\n"
            f"Host: <code>{settings.PROXMOX_HOST}</code>"
        )
    except Exception as e:
        text = f"❌ <b>Proxmox недоступен</b>\n\n<code>{e}</code>"

    await call.message.edit_text(text, reply_markup=back_kb("adm:settings"))


@router.callback_query(F.data == "adm:settings:ippool")
async def cb_adm_settings_ippool(call: CallbackQuery) -> None:
    """Статус IP пула."""
    await call.answer("⏳")

    from app.models import IpPool
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as session:
        total_r = await session.execute(select(func.count(IpPool.id)))
        total = total_r.scalar_one()
        free_r = await session.execute(
            select(func.count(IpPool.id)).where(IpPool.in_use == False)  # noqa
        )
        free = free_r.scalar_one()

        all_ips = await session.execute(
            select(IpPool).order_by(IpPool.ip)
        )
        ips = all_ips.scalars().all()

    icon = "🟢" if free > 2 else ("🟡" if free > 0 else "🔴")
    lines = [
        f"🌐 <b>IP пул</b>\n\n"
        f"{icon} Свободно: <b>{free}</b> / {total}\n\n"
        "Все адреса:\n"
    ]
    for ip in ips:
        status = "🔴 занят" if ip.in_use else "🟢 свободен"
        lines.append(f"  <code>{ip.ip}</code> — {status}")

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=back_kb("adm:settings"),
    )


@router.callback_query(F.data == "adm:settings:test_notify")
async def cb_adm_settings_test_notify(call: CallbackQuery) -> None:
    """Отправить тестовое уведомление в канал."""
    from app.services.notify import notify_error

    try:
        await notify_error(call.bot, "🧪 Тест уведомлений из админ-панели", "OK")
        await call.answer("✅ Уведомление отправлено в канал", show_alert=True)
    except Exception as e:
        await call.answer(f"❌ {e}", show_alert=True)


# ── Заглушка для noop кнопок (номера страниц) ────────────────
@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await call.answer()
