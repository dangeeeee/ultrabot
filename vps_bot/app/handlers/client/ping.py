"""
Команда /ping — проверить доступность VPS.

Делает ICMP ping через asyncio subprocess.
Показывает задержку и потерю пакетов.
"""
from __future__ import annotations
import asyncio
import re
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from app.core.database import AsyncSessionLocal
from app.repositories.vps import VpsRepository
from app.models import VpsStatus

logger = logging.getLogger(__name__)
router = Router(name="ping")

PING_COUNT = 4
PING_TIMEOUT = 10


async def _ping_host(ip: str) -> dict:
    """
    Запустить ping и вернуть результат.
    Работает на Linux (внутри Docker контейнера).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", str(PING_COUNT), "-W", "2", "-q", ip,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=PING_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            return {"reachable": False, "error": "timeout"}

        output = stdout.decode()

        # Парсим статистику: "4 packets transmitted, 4 received, 0% packet loss"
        loss_match = re.search(r"(\d+)% packet loss", output)
        loss_pct = int(loss_match.group(1)) if loss_match else 100

        # Парсим RTT: "rtt min/avg/max/mdev = 1.2/1.5/1.8/0.1 ms"
        rtt_match = re.search(r"rtt .+ = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", output)
        if rtt_match:
            rtt_min, rtt_avg, rtt_max, rtt_mdev = (float(x) for x in rtt_match.groups())
            return {
                "reachable": loss_pct < 100,
                "loss_pct": loss_pct,
                "rtt_min": rtt_min,
                "rtt_avg": rtt_avg,
                "rtt_max": rtt_max,
                "rtt_mdev": rtt_mdev,
            }

        return {"reachable": loss_pct < 100, "loss_pct": loss_pct}

    except FileNotFoundError:
        return {"reachable": None, "error": "ping not available"}
    except Exception as e:
        return {"reachable": False, "error": str(e)}


def _format_ping_result(ip: str, result: dict) -> str:
    if result.get("error") == "timeout":
        return f"⏱️ <b>Ping {ip}</b>\n\n❌ Таймаут ({PING_TIMEOUT}с) — сервер не отвечает"
    if result.get("error") == "ping not available":
        return f"⚠️ Команда ping недоступна в этой среде"
    if result.get("error"):
        return f"❌ Ошибка ping: {result['error']}"

    loss = result.get("loss_pct", 100)
    reachable = result.get("reachable", False)

    if not reachable:
        return (
            f"🔴 <b>Ping {ip}</b>\n\n"
            f"❌ Сервер недоступен\n"
            f"📦 Потеря пакетов: {loss}%"
        )

    avg = result.get("rtt_avg", 0)
    rtt_min = result.get("rtt_min", 0)
    rtt_max = result.get("rtt_max", 0)

    # Оценка качества
    if avg < 10:
        quality = "🟢 Отлично"
    elif avg < 50:
        quality = "🟡 Хорошо"
    elif avg < 150:
        quality = "🟠 Удовлетворительно"
    else:
        quality = "🔴 Плохо"

    lines = [
        f"🟢 <b>Ping {ip}</b>\n",
        f"⚡ Качество: {quality}",
        f"📊 Задержка avg: <b>{avg:.1f} мс</b>",
        f"📉 min: {rtt_min:.1f} мс  |  max: {rtt_max:.1f} мс",
    ]
    if loss > 0:
        lines.append(f"⚠️ Потеря пакетов: {loss}%")
    else:
        lines.append(f"✅ Потери пакетов: 0%")

    return "\n".join(lines)


@router.callback_query(F.data.startswith("ping:"))
async def cb_ping_vps(call: CallbackQuery) -> None:
    vps_id = int(call.data.split(":", 1)[1])

    async with AsyncSessionLocal() as session:
        vps = await VpsRepository(session).get_by_id(vps_id)

    if not vps or vps.telegram_id != call.from_user.id:
        await call.answer("VPS не найден", show_alert=True)
        return

    if vps.status != VpsStatus.ACTIVE:
        await call.answer("Сервер неактивен", show_alert=True)
        return

    await call.answer("⏳ Пингую...")
    msg = await call.message.answer(f"⏳ Проверяю доступность {vps.ip}...")

    result = await _ping_host(vps.ip)
    text = _format_ping_result(vps.ip, result)

    await msg.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить снова", callback_data=f"ping:{vps_id}")],
            [InlineKeyboardButton(text="◀️ К серверу", callback_data=f"vps:{vps_id}")],
        ]),
    )
