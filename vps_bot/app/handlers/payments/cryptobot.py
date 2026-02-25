"""
CryptoBot payment handler.
Флоу: выбор тарифа → pay:crypto:tariff → создание инвойса → FSM waiting_payment
→ пользователь жмёт "Я оплатил" → check:crypto:invoice_id → provision_vps
"""
from __future__ import annotations
import asyncio
import hashlib
import hmac
import logging
import aiohttp
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from app.core.config import settings, TARIFFS
from app.core.states import PaymentFSM
from app.core.database import AsyncSessionLocal
from app.repositories.user import PaymentRepository
from app.models import PaymentProvider
from app.services.vps_provision import provision_vps
from app.utils.keyboards import payment_confirm_kb, back_kb

logger = logging.getLogger(__name__)
router = Router(name="cryptobot")
API = "https://pay.crypt.bot/api"


async def _create_invoice(amount: float, description: str) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{API}/createInvoice",
            headers={"Crypto-Pay-API-Token": settings.CRYPTOBOT_TOKEN},
            json={
                "asset": "USDT",
                "amount": str(amount),
                "description": description,
                "expires_in": 3600,
            },
        ) as resp:
            data = await resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"CryptoBot error: {data.get('error', data)}")
    inv = data["result"]
    return {"invoice_id": str(inv["invoice_id"]), "pay_url": inv["pay_url"]}


async def _check_invoice_status(invoice_id: str) -> str:
    """Вернуть статус инвойса: active / paid / expired / cancelled"""
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"{API}/getInvoices",
            headers={"Crypto-Pay-API-Token": settings.CRYPTOBOT_TOKEN},
            params={"invoice_ids": invoice_id},
        ) as resp:
            data = await resp.json()
    items = data.get("result", {}).get("items", [])
    return items[0].get("status", "not_found") if items else "not_found"


def _verify_cryptobot_signature(body: bytes, signature: str) -> bool:
    secret = hashlib.sha256(settings.CRYPTOBOT_TOKEN.encode()).digest()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.callback_query(F.data.startswith("pay:crypto:"))
async def cb_pay_crypto(call: CallbackQuery, state: FSMContext) -> None:
    if not settings.CRYPTOBOT_ENABLED:
        await call.answer("Оплата крипто временно недоступна.", show_alert=True)
        return

    parts = call.data.split(":")   # pay:crypto:tariff_id[:renew_vps_id]
    tariff_id = parts[2]
    renew_vps_id = int(parts[3]) if len(parts) > 3 else None
    t = TARIFFS.get(tariff_id)
    if not t:
        await call.answer("Тариф не найден", show_alert=True)
        return

    await call.answer("⏳ Создаю счёт...")

    # ── Антифрод ─────────────────────────────────────────
    try:
        from app.services.antifrod import run_pre_payment_checks
        await run_pre_payment_checks(call.from_user.id)
    except Exception as af_err:
        from app.utils.keyboards import back_kb
        await call.message.edit_text(str(af_err), reply_markup=back_kb("tariffs"))
        return

    try:
        inv = await _create_invoice(
            t["price_usdt"],
            f"VPS {t['name']} — 1 месяц",
        )

        async with AsyncSessionLocal() as session:
            await PaymentRepository(session).create(
                telegram_id=call.from_user.id,
                external_id=inv["invoice_id"],
                provider=PaymentProvider.CRYPTOBOT,
                tariff=tariff_id,
                amount=t["price_usdt"],
                currency="USDT",
                renew_vps_id=renew_vps_id,
            )

        await state.set_state(PaymentFSM.waiting_payment)
        await state.update_data(
            invoice_id=inv["invoice_id"],
            provider="crypto",
            tariff_id=tariff_id,
            renew_vps_id=renew_vps_id,
        )

        await call.message.edit_text(
            f"💰 <b>Оплата USDT через @CryptoBot</b>\n\n"
            f"Тариф: <b>{t['name']}</b>\n"
            f"Сумма: <b>{t['price_usdt']} USDT</b>\n\n"
            f"<b>Как оплатить:</b>\n"
            f"1️⃣ Нажми кнопку <b>«Перейти к оплате»</b>\n"
            f"2️⃣ Оплати в @CryptoBot\n"
            f"3️⃣ Вернись и нажми <b>«✅ Я оплатил»</b>\n\n"
            f"⏰ Счёт действует 1 час",
            reply_markup=payment_confirm_kb(
                f"check:crypto:{inv['invoice_id']}",
                inv["pay_url"],
            ),
        )
    except Exception as e:
        logger.error(f"CryptoBot invoice creation error: {e}")
        await call.message.edit_text(
            "❌ <b>Ошибка создания счёта</b>\n\n"
            "Попробуй через несколько минут или выбери другой способ оплаты.",
            reply_markup=back_kb("tariffs"),
        )


@router.callback_query(F.data.startswith("check:crypto:"))
async def cb_check_crypto(call: CallbackQuery, state: FSMContext) -> None:
    invoice_id = call.data.split(":", 2)[2]
    await call.answer("⏳ Проверяю оплату...")

    status = await _check_invoice_status(invoice_id)

    if status == "paid":
        async with AsyncSessionLocal() as session:
            payment = await PaymentRepository(session).get_by_external_id(invoice_id)

        if not payment:
            await call.answer("❌ Платёж не найден в системе.", show_alert=True)
            return

        if payment.status.value == "paid":
            await call.message.edit_text(
                "✅ Этот платёж уже был обработан.\nПроверь /start → Мои серверы",
            )
            await state.clear()
            return

        await state.clear()
        await call.message.edit_text(
            "✅ <b>Оплата подтверждена!</b>\n\n"
            "⏳ Создаю сервер, это займёт около минуты...\n"
            "Я пришлю уведомление когда всё будет готово."
        )

        asyncio.create_task(
            provision_vps(
                call.bot,
                call.from_user.id,
                payment.tariff,
                invoice_id,
                payment.renew_vps_id,
            )
        )

    elif status == "active":
        await call.answer(
            "⏳ Оплата ещё не поступила.\n\n"
            "Убедись что оплатил в @CryptoBot и попробуй снова.",
            show_alert=True,
        )
    elif status in ("expired", "cancelled"):
        await state.clear()
        await call.message.edit_text(
            f"❌ <b>Счёт {'истёк' if status == 'expired' else 'отменён'}</b>\n\n"
            "Создай новый заказ через /start → Тарифы",
            reply_markup=back_kb("tariffs"),
        )
    else:
        await call.answer(f"Статус: {status}. Попробуй через минуту.", show_alert=True)
