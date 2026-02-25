"""
Payment webhooks — FastAPI роутер.
Caddy проксирует:
  POST /cryptobot-webhook  → CryptoBot HMAC-SHA256 верификация
  POST /yukassa-webhook    → YooKassa IP whitelist верификация
"""
from __future__ import annotations
import asyncio
import hashlib
import hmac
import ipaddress
import logging
from fastapi import APIRouter, Request, Header, HTTPException
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.repositories.user import PaymentRepository

logger = logging.getLogger(__name__)
router = APIRouter()

# Официальные IP YooKassa для webhook'ов
YUKASSA_ALLOWED_NETWORKS = [
    ipaddress.ip_network("185.71.76.0/27"),
    ipaddress.ip_network("185.71.77.0/27"),
    ipaddress.ip_network("77.75.153.0/25"),
    ipaddress.ip_network("77.75.156.11/32"),
    ipaddress.ip_network("77.75.156.35/32"),
    ipaddress.ip_network("77.75.154.128/25"),
    ipaddress.ip_network("2a02:5180::/32"),
]


def _ip_allowed_yukassa(ip_str: str) -> bool:
    """Проверяем что запрос пришёл с IP YooKassa."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in YUKASSA_ALLOWED_NETWORKS)
    except ValueError:
        return False


def _verify_cryptobot_signature(body: bytes, signature: str) -> bool:
    """HMAC-SHA256 верификация подписи CryptoBot."""
    if not settings.CRYPTOBOT_TOKEN or not signature:
        return False
    secret = hashlib.sha256(settings.CRYPTOBOT_TOKEN.encode()).digest()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.lower())


@router.post("/cryptobot-webhook")
async def handle_cryptobot_webhook(
    request: Request,
    crypto_pay_api_signature: str = Header(default=""),
) -> dict:
    body = await request.body()

    # ── Верификация подписи ──────────────────────────────
    if not _verify_cryptobot_signature(body, crypto_pay_api_signature):
        logger.warning(f"CryptoBot webhook: invalid signature from {request.client.host}")
        raise HTTPException(status_code=403, detail="Invalid signature")

    data = await request.json()
    update_type = data.get("update_type")

    if update_type != "invoice_paid":
        return {"ok": True}

    invoice_id = str(data["payload"]["invoice_id"])
    logger.info(f"CryptoBot webhook: invoice {invoice_id} paid")

    async with AsyncSessionLocal() as session:
        payment = await PaymentRepository(session).get_by_external_id(invoice_id)

    if not payment:
        logger.warning(f"CryptoBot webhook: payment {invoice_id} not found in DB")
        return {"ok": True}

    if payment.status.value == "paid":
        return {"ok": True}

    from app.services.vps_provision import provision_vps
    bot = request.app.state.bot
    asyncio.create_task(
        provision_vps(bot, payment.telegram_id, payment.tariff, invoice_id, payment.renew_vps_id)
    )
    return {"ok": True}


@router.post("/yukassa-webhook")
async def handle_yukassa_webhook(request: Request) -> dict:
    # ── IP верификация ───────────────────────────────────
    client_ip = request.headers.get("X-Real-IP") or (request.client.host if request.client else "")

    if settings.YUKASSA_ENABLED and not _ip_allowed_yukassa(client_ip):
        logger.warning(f"YooKassa webhook: forbidden IP {client_ip}")
        raise HTTPException(status_code=403, detail="Forbidden")

    data = await request.json()
    event = data.get("event", "")

    if event != "payment.succeeded":
        return {"ok": True}

    payment_id = data.get("object", {}).get("id")
    if not payment_id:
        raise HTTPException(status_code=400, detail="Missing payment id")

    logger.info(f"YooKassa webhook: payment {payment_id} succeeded")

    async with AsyncSessionLocal() as session:
        payment = await PaymentRepository(session).get_by_external_id(payment_id)

    if not payment:
        logger.warning(f"YooKassa webhook: payment {payment_id} not found in DB")
        return {"ok": True}

    if payment.status.value == "paid":
        return {"ok": True}

    from app.services.vps_provision import provision_vps
    bot = request.app.state.bot
    asyncio.create_task(
        provision_vps(bot, payment.telegram_id, payment.tariff, payment_id, payment.renew_vps_id)
    )
    return {"ok": True}
