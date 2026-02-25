"""
Все клавиатуры бота.

Соглашения:
  btn(text, cb)         — кнопка с callback_data
  btn(text, url=url)    — кнопка-ссылка
  kb(*rows)             — InlineKeyboardMarkup из строк кнопок

Callback-data префиксы:
  adm:*        — admin-панель (вложенная навигация)
  pay:*        — платёжный флоу
  vps:*        — управление конкретным VPS
  check:*      — проверка оплаты
  ping:*       — пинг VPS
  autorenew_*  — автопродление
"""
from __future__ import annotations
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.core.config import TARIFFS
from app.models import Vps
from datetime import datetime


# ── Хелперы ───────────────────────────────────────────────────

def btn(
    text: str,
    callback: str | None = None,
    url: str | None = None,
) -> InlineKeyboardButton:
    """Создать кнопку. Передай либо callback, либо url."""
    return InlineKeyboardButton(text=text, callback_data=callback, url=url)


def kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    """Собрать клавиатуру из строк."""
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def back_btn(target: str = "main_menu", label: str = "◀️ Назад") -> InlineKeyboardButton:
    """Стандартная кнопка «Назад»."""
    return btn(label, target)


def back_kb(target: str = "main_menu", label: str = "◀️ Назад") -> InlineKeyboardMarkup:
    """Клавиатура только с кнопкой «Назад»."""
    return kb([back_btn(target, label)])


# ═══════════════════════════════════════════════════════════════
# КЛИЕНТСКИЕ КЛАВИАТУРЫ
# ═══════════════════════════════════════════════════════════════

def main_menu_kb(referral_enabled: bool = True) -> InlineKeyboardMarkup:
    rows = [
        [btn("📦 Тарифы и цены", "tariffs")],
        [btn("🖥️ Мои серверы", "my_vps")],
    ]
    if referral_enabled:
        rows.append([btn("👥 Реферальная программа", "referral")])
    rows.append([btn("💬 Поддержка", "support")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tariffs_kb() -> InlineKeyboardMarkup:
    rows = [
        [btn(f"{t['emoji']} {t['name']} — {t['price_rub']} ₽ / {t['price_usdt']} USDT", f"tariff:{tid}")]
        for tid, t in TARIFFS.items()
    ]
    rows.append([back_btn("main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tariff_detail_kb(tariff_id: str) -> InlineKeyboardMarkup:
    return kb(
        [btn("🛒 Купить сейчас", f"buy:{tariff_id}")],
        [back_btn("tariffs", "◀️ К тарифам")],
    )


def payment_method_kb(tariff_id: str, renew_vps_id: int | None = None) -> InlineKeyboardMarkup:
    sfx = f":{renew_vps_id}" if renew_vps_id else ""
    return kb(
        [btn("💳 Карта РФ (ЮKassa)",         f"pay:yukassa:{tariff_id}{sfx}")],
        [btn("💰 Крипта USDT (CryptoBot)",    f"pay:crypto:{tariff_id}{sfx}")],
        [back_btn(f"tariff:{tariff_id}")],
    )


def payment_confirm_kb(check_cb: str, pay_url: str) -> InlineKeyboardMarkup:
    return kb(
        [btn("💳 Перейти к оплате", url=pay_url)],
        [btn("✅ Я оплатил", check_cb)],
        [back_btn("main_menu")],
    )


def my_vps_kb(vps_list: list) -> InlineKeyboardMarkup:
    rows = []
    for vps in vps_list:
        days = (vps.expires_at - datetime.utcnow()).days
        icon = "🟢" if vps.status.value == "active" and days > 0 else "🔴"
        t_name = TARIFFS.get(vps.tariff, {}).get("name", vps.tariff)
        rows.append([btn(f"{icon} {vps.ip} · {t_name} · {days}д.", f"vps:{vps.id}")])
    rows.append([back_btn("main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def vps_detail_kb(vps_id: int, tariff_id: str, autorenew: bool = False) -> InlineKeyboardMarkup:
    ar_label = "🔔 Автопродление: ВКЛ" if autorenew else "🔕 Автопродление: ВЫКЛ"
    return kb(
        [btn("🔄 Перезагрузить", f"vps_reboot:{vps_id}"),
         btn("⚡ Ping",          f"ping:{vps_id}")],
        [btn("💳 Продлить",      f"vps_renew:{vps_id}:{tariff_id}"),
         btn(ar_label,           f"autorenew_toggle:{vps_id}")],
        [back_btn("my_vps", "◀️ Мои серверы")],
    )


# ═══════════════════════════════════════════════════════════════
# ADMIN КЛАВИАТУРЫ
# Архитектура навигации:
#   adm:home → главный экран
#   adm:stats → статистика
#   adm:users → список пользователей
#   adm:users:search → поиск
#   adm:user:<id> → профиль пользователя
#   adm:vps → список VPS
#   adm:vps:<id> → карточка VPS
#   adm:broadcast → рассылка
#   adm:settings → настройки / Proxmox
#   adm:ippool → IP пул
# ═══════════════════════════════════════════════════════════════

def adm_home_kb() -> InlineKeyboardMarkup:
    """Главное меню админ-панели."""
    return kb(
        [btn("📊 Статистика",      "adm:stats")],
        [btn("👥 Пользователи",    "adm:users"),
         btn("🖥️ Серверы",         "adm:vps")],
        [btn("📢 Рассылка",        "adm:broadcast"),
         btn("⚙️ Настройки",       "adm:settings")],
        [back_btn("main_menu", "🏠 Главное меню")],
    )


def adm_stats_kb() -> InlineKeyboardMarkup:
    return kb(
        [btn("📈 Выручка 7д",  "adm:stats:7d"),
         btn("📈 Выручка 30д", "adm:stats:30d")],
        [btn("🏆 Топ тарифов", "adm:stats:tariffs")],
        [back_btn("adm:home")],
    )


def adm_users_kb(page: int = 0, has_next: bool = False) -> InlineKeyboardMarkup:
    """Меню раздела пользователей."""
    rows = [
        [btn("🔍 Поиск по ID",    "adm:users:find"),
         btn("🔍 Поиск по @",     "adm:users:find_username")],
        [btn("📋 Последние 10",   "adm:users:recent"),
         btn("🚫 Забаненные",     "adm:users:banned")],
    ]
    # Пагинация
    nav = []
    if page > 0:
        nav.append(btn("◀", f"adm:users:page:{page - 1}"))
    nav.append(btn(f"стр. {page + 1}", "noop"))
    if has_next:
        nav.append(btn("▶", f"adm:users:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([back_btn("adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def adm_user_profile_kb(telegram_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    """Кнопки на карточке пользователя."""
    ban_label = "✅ Разбанить" if is_banned else "🚫 Заблокировать"
    ban_cb    = f"adm:user:unban:{telegram_id}" if is_banned else f"adm:user:ban:{telegram_id}"
    return kb(
        [btn("🖥️ Серверы юзера",  f"adm:user:vps:{telegram_id}")],
        [btn(ban_label,            ban_cb),
         btn("✉️ Написать",        f"adm:user:msg:{telegram_id}")],
        [back_btn("adm:users")],
    )


def adm_user_vps_kb(vps_list: list, telegram_id: int) -> InlineKeyboardMarkup:
    """Серверы конкретного пользователя в контексте админа."""
    rows = [
        [btn(f"{'🟢' if v.status.value == 'active' else '🔴'} #{v.id} {v.ip}",
             f"adm:vps:{v.id}")]
        for v in vps_list
    ]
    rows.append([back_btn(f"adm:user:{telegram_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def adm_vps_kb(page: int = 0, has_next: bool = False) -> InlineKeyboardMarkup:
    """Меню раздела серверов."""
    rows = [
        [btn("🟢 Активные",    "adm:vps:filter:active"),
         btn("🔴 Истёкшие",    "adm:vps:filter:expired")],
        [btn("🔍 Найти по IP", "adm:vps:find")],
    ]
    nav = []
    if page > 0:
        nav.append(btn("◀", f"adm:vps:page:{page - 1}"))
    nav.append(btn(f"стр. {page + 1}", "noop"))
    if has_next:
        nav.append(btn("▶", f"adm:vps:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([back_btn("adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def adm_vps_card_kb(vps_id: int, telegram_id: int) -> InlineKeyboardMarkup:
    """Действия на карточке VPS в контексте админа."""
    return kb(
        [btn("🔄 Перезагрузить",  f"adm:vps:reboot:{vps_id}"),
         btn("⚡ Ping",            f"adm:vps:ping:{vps_id}")],
        [btn("🗑️ Удалить",         f"adm:vps:delete:{vps_id}"),
         btn("👤 Профиль юзера",   f"adm:user:{telegram_id}")],
        [back_btn("adm:vps")],
    )


def adm_settings_kb() -> InlineKeyboardMarkup:
    """Меню настроек."""
    return kb(
        [btn("🖥️ Proxmox статус",  "adm:settings:proxmox")],
        [btn("🌐 IP пул",          "adm:settings:ippool")],
        [btn("🔔 Тест уведомлений", "adm:settings:test_notify")],
        [back_btn("adm:home")],
    )


def adm_confirm_kb(yes_cb: str, no_cb: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения опасного действия."""
    return kb(
        [btn("✅ Да, подтверждаю", yes_cb),
         btn("❌ Отмена",          no_cb)],
    )
