"""
YooKassa payment handler.
Флоу: pay:yukassa:tariff → создание платежа → FSM waiting_payment
→ "Я оплатил" → проверка статуса → provision_vps

Верификация webhook: YooKassa шлёт уведомления с IP из белого списка.
Мы проверяем IP + парсим тело запроса.
"""
from __future__ import annotations
import asyncio
import base64
import logging
import uuid
import aiohttp
from aiogram import Router, F
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
router = Router(name="yukassa")
API = "https://api.yookassa.ru/v3"

# IP белый список YooKassa (официальный)
YUKASSA_IPS = {
    "185.71.76.0/27",
    "185.71.77.0/27",
    "77.75.153.0/25",
    "77.75.156.11",
    "77.75.156.35",
    "77.75.154.128/25",
    "2a02:5180::/32",
}


def _auth() -> str:
    creds = f"{settings.YUKASSA_SHOP_ID}:{settings.YUKASSA_SECRET_KEY}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


async def _create_payment(amount_rub: float, description: str, metadata: dict) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{API}/payments",
            headers={
                "Authorization": _auth(),
                "Idempotence-Key": str(uuid.uuid4()),
                "Content-Type": "application/json",
            },
            json={
                "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
                "confirmation": {
                    "type": "redirect",
                    "return_url": "https://t.me",
                },
                "description": description,
                "metadata": metadata,
                "capture": True,
            },
        ) as resp:
            data = await resp.json()

    if "id" not in data:
        err = data.get("description", str(data))
        raise RuntimeError(f"YooKassa: {err}")

    return {
        "payment_id": data["id"],
        "pay_url": data["confirmation"]["confirmation_url"],
        "status": data["status"],
    }


async def _get_payment_status(payment_id: str) -> str:
    """Вернуть статус: pending / waiting_for_capture / succeeded / canceled"""
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"{API}/payments/{payment_id}",
            headers={"Authorization": _auth()},
        ) as resp:
            data = await resp.json()
    return data.get("status", "unknown")


@router.callback_query(F.data.startswith("pay:yukassa:"))
async def cb_pay_yukassa(call: CallbackQuery, state: FSMContext) -> None:
    if not settings.YUKASSA_ENABLED:
        await call.answer("Оплата картой временно недоступна.", show_alert=True)
        return

    parts = call.data.split(":")  # pay:yukassa:tariff_id[:renew_vps_id]
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
        result = await _create_payment(
            t["price_rub"],
            f"VPS {t['name']} — 1 месяц",
            {
                "telegram_id": str(call.from_user.id),
                "tariff": tariff_id,
                "renew_vps_id": str(renew_vps_id or ""),
            },
        )

        async with AsyncSessionLocal() as session:
            await PaymentRepository(session).create(
                telegram_id=call.from_user.id,
                external_id=result["payment_id"],
                provider=PaymentProvider.YUKASSA,
                tariff=tariff_id,
                amount=t["price_rub"],
                currency="RUB",
                renew_vps_id=renew_vps_id,
            )

        await state.set_state(PaymentFSM.waiting_payment)
        await state.update_data(
            payment_id=result["payment_id"],
            provider="yukassa",
            tariff_id=tariff_id,
            renew_vps_id=renew_vps_id,
        )

        await call.message.edit_text(
            f"💳 <b>Оплата картой РФ (ЮKassa)</b>\n\n"
            f"Тариф: <b>{t['name']}</b>\n"
            f"Сумма: <b>{t['price_rub']} ₽</b>\n\n"
            f"<b>Как оплатить:</b>\n"
            f"1️⃣ Нажми <b>«Перейти к оплате»</b>\n"
            f"2️⃣ Введи данные карты\n"
            f"3️⃣ Вернись и нажми <b>«✅ Я оплатил»</b>\n\n"
            f"✅ Принимаем: Visa, MasterCard, Мир, СБП",
            reply_markup=payment_confirm_kb(
                f"check:yukassa:{result['payment_id']}",
                result["pay_url"],
            ),
        )
    except Exception as e:
        logger.error(f"YooKassa payment creation error: {e}")
        await call.message.edit_text(
            "❌ <b>Ошибка создания счёта</b>\n\n"
            "Попробуй через несколько минут или выбери другой способ оплаты.",
            reply_markup=back_kb("tariffs"),
        )


@router.callback_query(F.data.startswith("check:yukassa:"))
async def cb_check_yukassa(call: CallbackQuery, state: FSMContext) -> None:
    payment_id = call.data.split(":", 2)[2]
    await call.answer("⏳ Проверяю оплату...")

    status = await _get_payment_status(payment_id)

    if status in ("succeeded", "waiting_for_capture"):
        async with AsyncSessionLocal() as session:
            payment = await PaymentRepository(session).get_by_external_id(payment_id)

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
                payment_id,
                payment.renew_vps_id,
            )
        )

    elif status == "pending":
        await call.answer(
            "⏳ Оплата ещё обрабатывается.\n\n"
            "Подожди 1-2 минуты и проверь снова.",
            show_alert=True,
        )
    elif status == "canceled":
        await state.clear()
        await call.message.edit_text(
            "❌ <b>Платёж отменён</b>\n\n"
            "Создай новый заказ через /start → Тарифы",
            reply_markup=back_kb("tariffs"),
        )
    else:
        await call.answer(f"Статус: {status}. Попробуй ещё раз.", show_alert=True)
