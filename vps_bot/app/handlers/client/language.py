from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from app.core.i18n import set_lang, get_lang, t

router = Router(name="language")


def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang:ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang:en"),
        ],
        [InlineKeyboardButton(text="◀️ Back / Назад", callback_data="main_menu")],
    ])


@router.callback_query(F.data == "language")
async def cb_language(call: CallbackQuery) -> None:
    lang = await get_lang(call.from_user.id)
    current = "🇷🇺 Русский" if lang == "ru" else "🇬🇧 English"
    await call.message.edit_text(
        f"🌐 <b>Язык / Language</b>\n\nТекущий / Current: <b>{current}</b>",
        reply_markup=lang_kb(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("setlang:"))
async def cb_set_lang(call: CallbackQuery) -> None:
    lang = call.data.split(":")[1]
    if lang not in ("ru", "en"):
        await call.answer("Unknown language", show_alert=True)
        return

    await set_lang(call.from_user.id, lang)
    await call.answer(t("lang_changed", lang), show_alert=True)

    # Обновляем главное меню на новом языке
    from app.handlers.client.start import main_menu_kb
    from app.core.config import settings
    await call.message.edit_text(
        t("welcome", lang).format(name=call.from_user.first_name),
        reply_markup=main_menu_kb(settings.REFERRAL_ENABLED),
    )
