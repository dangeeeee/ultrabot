"""
Управление серверами пользователя.
/start → Мои серверы → выбор VPS → детали → действия
"""
from __future__ import annotations
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from app.core.database import AsyncSessionLocal
from app.repositories.vps import VpsRepository
from app.services.proxmox import proxmox_service
from app.services.autorenew import AutoRenewRepository
from app.core.config import TARIFFS

router = Router(name="my_vps")


def _vps_list_kb(vps_list) -> InlineKeyboardMarkup:
    rows = []
    for vps in vps_list:
        days = (vps.expires_at - datetime.utcnow()).days
        icon = "🟢" if vps.status.value == "active" and days > 0 else "🔴"
        label = f"{icon} {vps.ip}  ({days}д.)  {TARIFFS.get(vps.tariff, {}).get('name', vps.tariff)}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"vps:{vps.id}")])
    rows.append([InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _build_vps_detail_kb(
    vps_id: int,
    tariff_id: str,
    autorenew_enabled: bool = False,
) -> InlineKeyboardMarkup:
    ar_btn = (
        InlineKeyboardButton(text="🔔 Автопродление: ВКЛ", callback_data=f"autorenew_toggle:{vps_id}")
        if autorenew_enabled
        else InlineKeyboardButton(text="🔕 Автопродление: ВЫКЛ", callback_data=f"autorenew_toggle:{vps_id}")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Перезагрузить", callback_data=f"vps_reboot:{vps_id}"),
            InlineKeyboardButton(text="⚡ Ping", callback_data=f"ping:{vps_id}"),
        ],
        [
            InlineKeyboardButton(text="💳 Продлить", callback_data=f"vps_renew:{vps_id}:{tariff_id}"),
            ar_btn,
        ],
        [InlineKeyboardButton(text="◀️ Мои серверы", callback_data="my_vps")],
    ])


@router.callback_query(F.data == "my_vps")
async def cb_my_vps(call: CallbackQuery) -> None:
    async with AsyncSessionLocal() as session:
        vps_list = await VpsRepository(session).get_user_vps(call.from_user.id)

    if not vps_list:
        await call.message.edit_text(
            "🖥️ <b>Мои серверы</b>\n\nУ тебя пока нет серверов.\n\nКупи первый VPS! 👇",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 Смотреть тарифы", callback_data="tariffs")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
            ]),
        )
        return

    await call.message.edit_text(
        f"🖥️ <b>Мои серверы</b> — {len(vps_list)} шт.\n\nВыбери сервер:",
        reply_markup=_vps_list_kb(vps_list),
    )
    await call.answer()


@router.callback_query(F.data.startswith("vps:"))
async def cb_vps_detail(call: CallbackQuery) -> None:
    vps_id = int(call.data.split(":", 1)[1])

    async with AsyncSessionLocal() as session:
        vps = await VpsRepository(session).get_by_id(vps_id)
        ar = await AutoRenewRepository(session).get(vps_id)

    if not vps or vps.telegram_id != call.from_user.id:
        await call.answer("Сервер не найден", show_alert=True)
        return

    autorenew_on = ar.enabled if ar else False

    # Получаем статус из Proxmox
    try:
        st = await proxmox_service.status_lxc(vps.vmid)
        running = st["running"]
        status_icon = "🟢" if running else "🔴"
        status_str = "Работает" if running else "Остановлен"
        cpu_str = f"CPU: {st['cpu_pct']}%"
        ram_str = f"RAM: {st['mem_used_mb']}/{st['mem_total_mb']} MB"
        uptime_h = st["uptime_sec"] // 3600
        proxmox_line = f"{status_icon} {status_str} · {cpu_str} · {ram_str}\n⏱️ Аптайм: {uptime_h}ч"
    except Exception:
        proxmox_line = "⚠️ Статус недоступен"

    days = (vps.expires_at - datetime.utcnow()).days
    expire_icon = "📅" if days > 3 else ("⚠️" if days > 0 else "🔴")
    t = TARIFFS.get(vps.tariff, {})

    text = (
        f"🖥️ <b>Сервер #{vps.id}</b>\n\n"
        f"{proxmox_line}\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌐 IP: <code>{vps.ip}</code>\n"
        f"👤 Логин: <code>root</code>\n"
        f"🔑 Пароль: <code>{vps.password}</code>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Тариф: <b>{t.get('name', vps.tariff)}</b>\n"
        f"⚙️ {t.get('cpu', '?')} vCPU · {(t.get('ram', 0) // 1024)}GB RAM · {t.get('disk', '?')}GB SSD\n"
        f"{expire_icon} Активен до: <b>{vps.expires_at.strftime('%d.%m.%Y')}</b> ({days} дн.)\n\n"
        f"🔌 <code>ssh root@{vps.ip}</code>"
    )

    await call.message.edit_text(
        text,
        reply_markup=await _build_vps_detail_kb(vps_id, vps.tariff, autorenew_on),
    )
    await call.answer()


@router.callback_query(F.data.startswith("vps_reboot:"))
async def cb_vps_reboot(call: CallbackQuery) -> None:
    vps_id = int(call.data.split(":", 1)[1])

    async with AsyncSessionLocal() as session:
        vps = await VpsRepository(session).get_by_id(vps_id)

    if not vps or vps.telegram_id != call.from_user.id:
        await call.answer("Сервер не найден", show_alert=True)
        return

    await call.answer("⏳ Перезагружаю...")

    try:
        await proxmox_service.reboot_lxc(vps.vmid)
        await call.message.answer(
            f"✅ <b>Сервер перезагружен</b>\n\n"
            f"🌐 IP: <code>{vps.ip}</code>\n"
            f"⏳ Будет доступен через 30–60 секунд"
        )
    except Exception as e:
        await call.message.answer(f"❌ <b>Ошибка перезагрузки</b>\n<code>{e}</code>")


@router.callback_query(F.data.startswith("vps_renew:"))
async def cb_vps_renew(call: CallbackQuery) -> None:
    parts = call.data.split(":")
    vps_id, tariff_id = int(parts[1]), parts[2]

    async with AsyncSessionLocal() as session:
        vps = await VpsRepository(session).get_by_id(vps_id)

    if not vps or vps.telegram_id != call.from_user.id:
        await call.answer("Сервер не найден", show_alert=True)
        return

    t = TARIFFS.get(tariff_id, {})
    await call.message.edit_text(
        f"🔄 <b>Продление сервера</b>\n\n"
        f"🌐 IP: <code>{vps.ip}</code>\n"
        f"📦 Тариф: <b>{t.get('name', tariff_id)}</b>\n\n"
        f"💰 Стоимость:\n"
        f"  💳 Карта РФ: <b>{t.get('price_rub', '?')} ₽</b>\n"
        f"  💰 USDT: <b>{t.get('price_usdt', '?')}</b>\n\n"
        f"Выбери способ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Карта РФ (ЮKassa)", callback_data=f"pay:yukassa:{tariff_id}:{vps_id}")],
            [InlineKeyboardButton(text="💰 USDT (CryptoBot)", callback_data=f"pay:crypto:{tariff_id}:{vps_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"vps:{vps_id}")],
        ]),
    )
    await call.answer()
