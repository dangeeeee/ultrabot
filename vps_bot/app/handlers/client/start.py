from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from app.core.config import settings
from app.core.i18n import get_lang, t

router = Router(name="start")


async def main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    lang = await get_lang(user_id)
    rows = [
        [InlineKeyboardButton(text=t("btn_tariffs", lang), callback_data="tariffs")],
        [InlineKeyboardButton(text=t("btn_my_vps", lang), callback_data="my_vps")],
    ]
    if settings.REFERRAL_ENABLED:
        rows.append([InlineKeyboardButton(text=t("btn_referral", lang), callback_data="referral")])
    rows.append([InlineKeyboardButton(text=t("btn_support", lang), callback_data="support")])
    rows.append([
        InlineKeyboardButton(text=t("btn_language", lang), callback_data="language"),
        InlineKeyboardButton(text="🔄 Автопродление", callback_data="autorenew_settings"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject | None = None) -> None:
    # Реферальный deeplink
    if command and command.args and command.args.startswith("ref") and settings.REFERRAL_ENABLED:
        try:
            referrer_id = int(command.args[3:])
            if referrer_id != message.from_user.id:
                from app.core.database import AsyncSessionLocal
                from app.services.referral import ReferralRepository
                async with AsyncSessionLocal() as session:
                    added = await ReferralRepository(session).register_referral(
                        referrer_id, message.from_user.id
                    )
                if added:
                    try:
                        await message.bot.send_message(
                            referrer_id,
                            f"🎉 По твоей ссылке зарегистрировался новый пользователь!\n"
                            f"Когда он купит VPS, ты получишь бонус "
                            f"<b>{settings.REFERRAL_BONUS_RUB:.0f} ₽</b>.",
                        )
                    except Exception:
                        pass
        except (ValueError, IndexError):
            pass

    lang = await get_lang(message.from_user.id)
    kb = await main_menu_kb(message.from_user.id)
    await message.answer(
        t("welcome", lang).format(name=message.from_user.first_name),
        reply_markup=kb,
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery) -> None:
    lang = await get_lang(call.from_user.id)
    kb = await main_menu_kb(call.from_user.id)
    await call.message.edit_text(
        t("welcome", lang).format(name=call.from_user.first_name),
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery) -> None:
    lang = await get_lang(call.from_user.id)
    await call.message.edit_text(
        t("support", lang).format(
            support=settings.SUPPORT_USERNAME,
            user_id=call.from_user.id,
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_back", lang), callback_data="main_menu")]
        ]),
    )
    await call.answer()
