"""
Простая i18n система без внешних зависимостей.

Использование:
    from app.core.i18n import t, get_lang, set_lang

    lang = await get_lang(telegram_id)
    text = t("welcome", lang).format(name="Иван")
    await set_lang(telegram_id, "en")
"""
from __future__ import annotations
import logging
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

STRINGS: dict[str, dict[str, str]] = {
    # ── Start / Menu ──────────────────────────────────────────
    "welcome": {
        "ru": "👋 Привет, <b>{name}</b>!\n\n🖥️ <b>VPS Shop</b> — виртуальные серверы мгновенно\n\n⚡ Создание ~1 мин • 🌍 Германия • 🐧 Ubuntu 22.04\n🔒 Полный root доступ\n\nВыбери действие:",
        "en": "👋 Hello, <b>{name}</b>!\n\n🖥️ <b>VPS Shop</b> — instant virtual servers\n\n⚡ Setup ~1 min • 🌍 Germany • 🐧 Ubuntu 22.04\n🔒 Full root access\n\nChoose an action:",
    },
    "btn_tariffs": {"ru": "📦 Тарифы и цены", "en": "📦 Plans & Pricing"},
    "btn_my_vps": {"ru": "🖥️ Мои серверы", "en": "🖥️ My Servers"},
    "btn_referral": {"ru": "👥 Реферальная программа", "en": "👥 Referral Program"},
    "btn_support": {"ru": "💬 Поддержка", "en": "💬 Support"},
    "btn_language": {"ru": "🌐 Язык / Language", "en": "🌐 Язык / Language"},

    # ── Tariffs ───────────────────────────────────────────────
    "tariffs_header": {
        "ru": "📦 <b>Тарифы VPS</b>\n\nВсе серверы на <b>Hetzner</b> (Германия)\n🐧 Ubuntu 22.04 • 🌐 1 Гбит/с\n\nВыбери тариф:",
        "en": "📦 <b>VPS Plans</b>\n\nAll servers on <b>Hetzner</b> (Germany)\n🐧 Ubuntu 22.04 • 🌐 1 Gbit/s\n\nChoose a plan:",
    },
    "btn_buy": {"ru": "🛒 Купить", "en": "🛒 Buy"},
    "btn_back": {"ru": "◀️ Назад", "en": "◀️ Back"},
    "btn_back_tariffs": {"ru": "◀️ К тарифам", "en": "◀️ To plans"},

    # ── Payment ───────────────────────────────────────────────
    "choose_payment": {
        "ru": "💳 <b>Выбери способ оплаты</b>\n\nТариф: <b>{tariff}</b>",
        "en": "💳 <b>Choose payment method</b>\n\nPlan: <b>{tariff}</b>",
    },
    "btn_pay_card": {"ru": "💳 Карта РФ (ЮKassa)", "en": "💳 Card (YooKassa)"},
    "btn_pay_crypto": {"ru": "💰 Крипта USDT (CryptoBot)", "en": "💰 Crypto USDT (CryptoBot)"},
    "btn_promo": {"ru": "🎫 У меня есть промокод", "en": "🎫 I have a promo code"},
    "payment_confirmed": {
        "ru": "✅ <b>Оплата подтверждена!</b>\n\n⏳ Создаю сервер, это займёт около минуты...",
        "en": "✅ <b>Payment confirmed!</b>\n\n⏳ Setting up your server, about a minute...",
    },
    "payment_not_found": {
        "ru": "⏳ Оплата ещё не поступила. Убедись что оплатил и попробуй снова.",
        "en": "⏳ Payment not received yet. Make sure you paid and try again.",
    },

    # ── VPS ───────────────────────────────────────────────────
    "my_vps_empty": {
        "ru": "🖥️ <b>Мои серверы</b>\n\nУ тебя пока нет серверов.\nКупи первый VPS! 👇",
        "en": "🖥️ <b>My Servers</b>\n\nYou don't have any servers yet.\nBuy your first VPS! 👇",
    },
    "vps_ready": {
        "ru": (
            "🎉 <b>Твой сервер готов!</b>\n\n"
            "📦 Тариф: <b>{tariff}</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "🌐 IP: <code>{ip}</code>\n"
            "👤 Логин: <code>root</code>\n"
            "🔑 Пароль: <code>{password}</code>\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "🔌 SSH: <code>ssh root@{ip}</code>\n\n"
            "📅 Активен до: <b>{expires}</b>"
        ),
        "en": (
            "🎉 <b>Your server is ready!</b>\n\n"
            "📦 Plan: <b>{tariff}</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "🌐 IP: <code>{ip}</code>\n"
            "👤 Login: <code>root</code>\n"
            "🔑 Password: <code>{password}</code>\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "🔌 SSH: <code>ssh root@{ip}</code>\n\n"
            "📅 Active until: <b>{expires}</b>"
        ),
    },
    "vps_renewed": {
        "ru": "✅ <b>Сервер продлён на 30 дней!</b>\n\n🌐 IP: <code>{ip}</code>\n📅 Активен до: <b>{expires}</b>",
        "en": "✅ <b>Server extended by 30 days!</b>\n\n🌐 IP: <code>{ip}</code>\n📅 Active until: <b>{expires}</b>",
    },
    "vps_expired_notice": {
        "ru": "❌ <b>Сервер удалён</b>\n\nVPS <code>{ip}</code> удалён — срок истёк.\nКупи новый: /start → Тарифы",
        "en": "❌ <b>Server deleted</b>\n\nVPS <code>{ip}</code> was deleted — subscription expired.\nBuy new: /start → Plans",
    },
    "expire_3d": {
        "ru": "⚠️ <b>Твой VPS истекает через 3 дня!</b>\n\n🌐 IP: <code>{ip}</code>\n📅 Истекает: <b>{date}</b>\n\n👉 /start → Мои серверы → Продлить",
        "en": "⚠️ <b>Your VPS expires in 3 days!</b>\n\n🌐 IP: <code>{ip}</code>\n📅 Expires: <b>{date}</b>\n\n👉 /start → My Servers → Renew",
    },
    "expire_1d": {
        "ru": "🚨 <b>Твой VPS истекает завтра!</b>\n\n🌐 IP: <code>{ip}</code>\n📅 Истекает: <b>{date}</b>\n\n⚡ Срочно продли: /start → Мои серверы",
        "en": "🚨 <b>Your VPS expires tomorrow!</b>\n\n🌐 IP: <code>{ip}</code>\n📅 Expires: <b>{date}</b>\n\n⚡ Renew now: /start → My Servers",
    },

    # ── Support ───────────────────────────────────────────────
    "support": {
        "ru": "💬 <b>Поддержка</b>\n\nПиши: {support}\n\n🕐 Время ответа: 1–2 часа\n📋 Твой Telegram ID: <code>{user_id}</code>",
        "en": "💬 <b>Support</b>\n\nContact: {support}\n\n🕐 Response time: 1–2 hours\n📋 Your Telegram ID: <code>{user_id}</code>",
    },

    # ── Language select ───────────────────────────────────────
    "lang_changed": {
        "ru": "✅ Язык изменён на <b>Русский</b>",
        "en": "✅ Language changed to <b>English</b>",
    },

    # ── Referral ──────────────────────────────────────────────
    "referral_header": {
        "ru": (
            "👥 <b>Реферальная программа</b>\n\n"
            "За каждого друга который купит VPS — бонус:\n"
            "  💳 <b>{bonus_rub} ₽</b> или <b>{bonus_usdt} USDT</b>\n\n"
            "━━━━━━━━━━━━━━━━━\n"
            "📊 Статистика:\n"
            "  👤 Приглашено: <b>{total}</b>\n"
            "  ✅ Купили VPS: <b>{paid}</b>\n"
            "  💰 Баланс: <b>{balance:.2f} ₽</b>\n\n"
            "🔗 Твоя ссылка:\n<code>{link}</code>"
        ),
        "en": (
            "👥 <b>Referral Program</b>\n\n"
            "For each friend who buys VPS — bonus:\n"
            "  💳 <b>{bonus_rub} RUB</b> or <b>{bonus_usdt} USDT</b>\n\n"
            "━━━━━━━━━━━━━━━━━\n"
            "📊 Stats:\n"
            "  👤 Invited: <b>{total}</b>\n"
            "  ✅ Purchased: <b>{paid}</b>\n"
            "  💰 Balance: <b>{balance:.2f} RUB</b>\n\n"
            "🔗 Your link:\n<code>{link}</code>"
        ),
    },

    # ── Errors ────────────────────────────────────────────────
    "error_generic": {
        "ru": "⚠️ Что-то пошло не так. Попробуй ещё раз или обратись в поддержку.",
        "en": "⚠️ Something went wrong. Try again or contact support.",
    },
    "banned": {
        "ru": "🚫 Ваш аккаунт заблокирован. Обратитесь в поддержку.",
        "en": "🚫 Your account is banned. Contact support.",
    },
    "rate_limit": {
        "ru": "⏳ Слишком много запросов. Подожди минуту.",
        "en": "⏳ Too many requests. Wait a minute.",
    },
}

DEFAULT_LANG = "ru"


def t(key: str, lang: str = DEFAULT_LANG) -> str:
    """Получить перевод по ключу."""
    strings = STRINGS.get(key, {})
    return strings.get(lang) or strings.get(DEFAULT_LANG) or f"[{key}]"


async def get_lang(telegram_id: int) -> str:
    """Получить язык пользователя из Redis."""
    try:
        redis = await get_redis()
        val = await redis.get(f"lang:{telegram_id}")
        return val if val in ("ru", "en") else DEFAULT_LANG
    except Exception:
        return DEFAULT_LANG


async def set_lang(telegram_id: int, lang: str) -> None:
    """Сохранить язык пользователя в Redis."""
    try:
        redis = await get_redis()
        await redis.set(f"lang:{telegram_id}", lang, ex=86400 * 365)
    except Exception as e:
        logger.warning(f"set_lang failed: {e}")
