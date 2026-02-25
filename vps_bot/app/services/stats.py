"""
Статистика бота с ASCII-графиками для Telegram.

Команда /stats — полная статистика для администратора:
- Выручка за сегодня/неделю/месяц
- График продаж за последние 14 дней (ASCII bars)
- Распределение по тарифам (pie в тексте)
- Активных / истекающих / просроченных VPS
- Топ активных пользователей
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Payment, PaymentStatus, Vps, VpsStatus, User

logger = logging.getLogger(__name__)


def _bar(value: float, max_value: float, width: int = 12) -> str:
    """ASCII progress bar: ████░░░░░░░░"""
    if max_value == 0:
        filled = 0
    else:
        filled = round(value / max_value * width)
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _sparkline(values: list[float]) -> str:
    """ASCII спарклайн из 8 символов: ▁▂▃▄▅▆▇█"""
    chars = "▁▂▃▄▅▆▇█"
    if not values or max(values) == 0:
        return "▁" * len(values)
    mx = max(values)
    return "".join(chars[min(7, round(v / mx * 7))] for v in values)


async def get_full_stats(session: AsyncSession) -> str:
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start - timedelta(days=30)

    # ── Выручка ───────────────────────────────────────────────
    async def revenue(since: datetime) -> float:
        r = await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .where(Payment.status == PaymentStatus.PAID)
            .where(Payment.created_at >= since)
        )
        return float(r.scalar_one())

    rev_today = await revenue(today_start)
    rev_week = await revenue(week_start)
    rev_month = await revenue(month_start)

    # ── Пользователи ──────────────────────────────────────────
    total_users_r = await session.execute(select(func.count(User.id)))
    total_users = total_users_r.scalar_one()

    new_today_r = await session.execute(
        select(func.count(User.id)).where(User.created_at >= today_start)
    )
    new_today = new_today_r.scalar_one()

    new_week_r = await session.execute(
        select(func.count(User.id)).where(User.created_at >= week_start)
    )
    new_week = new_week_r.scalar_one()

    # ── VPS ───────────────────────────────────────────────────
    active_r = await session.execute(
        select(func.count(Vps.id))
        .where(Vps.status == VpsStatus.ACTIVE)
        .where(Vps.expires_at > now)
    )
    active_vps = active_r.scalar_one()

    expiring_r = await session.execute(
        select(func.count(Vps.id))
        .where(Vps.status == VpsStatus.ACTIVE)
        .where(Vps.expires_at > now)
        .where(Vps.expires_at <= now + timedelta(days=3))
    )
    expiring_vps = expiring_r.scalar_one()

    total_paid_r = await session.execute(
        select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PAID)
    )
    total_paid = total_paid_r.scalar_one()

    # ── График продаж за 14 дней ──────────────────────────────
    daily_data: dict[str, float] = {}
    for i in range(13, -1, -1):
        day = today_start - timedelta(days=i)
        day_end = day + timedelta(days=1)
        r = await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .where(Payment.status == PaymentStatus.PAID)
            .where(Payment.created_at >= day)
            .where(Payment.created_at < day_end)
        )
        daily_data[day.strftime("%d.%m")] = float(r.scalar_one())

    days = list(daily_data.keys())
    amounts = list(daily_data.values())
    max_amount = max(amounts) if amounts else 1

    # Строим ASCII график (2 строки на день)
    chart_rows = ["📈 <b>Продажи за 14 дней</b>\n<code>"]
    chart_rows.append("Дата   │Сумма         │")
    chart_rows.append("───────┼──────────────┤")
    for date, amount in zip(days, amounts):
        bar = _bar(amount, max_amount, 12)
        chart_rows.append(f"{date}  │{bar}│ {amount:>7.0f}")
    chart_rows.append("</code>")

    # Спарклайн последних 14 дней
    spark = _sparkline(amounts)
    chart_rows.append(f"\nТренд: <code>{spark}</code>")

    # ── Распределение по тарифам ──────────────────────────────
    from app.core.config import TARIFFS
    tariff_lines = ["📦 <b>По тарифам (активные):</b>"]
    tariff_total_r = await session.execute(
        select(func.count(Vps.id)).where(Vps.status == VpsStatus.ACTIVE)
    )
    tariff_total = max(tariff_total_r.scalar_one(), 1)

    for tid, t in TARIFFS.items():
        cnt_r = await session.execute(
            select(func.count(Vps.id))
            .where(Vps.status == VpsStatus.ACTIVE)
            .where(Vps.tariff == tid)
        )
        cnt = cnt_r.scalar_one()
        pct = cnt / tariff_total * 100
        bar = _bar(cnt, tariff_total, 8)
        tariff_lines.append(f"  {t['emoji']} {t['name']}: <b>{cnt}</b> <code>{bar}</code> {pct:.0f}%")

    # ── Сборка текста ─────────────────────────────────────────
    lines = [
        "📊 <b>Статистика VPS Shop</b>",
        f"<i>{now.strftime('%d.%m.%Y %H:%M')} UTC</i>\n",

        "💰 <b>Выручка:</b>",
        f"  Сегодня:   <b>{rev_today:>8.2f}</b>",
        f"  7 дней:    <b>{rev_week:>8.2f}</b>",
        f"  30 дней:   <b>{rev_month:>8.2f}</b>\n",

        "👥 <b>Пользователи:</b>",
        f"  Всего:     <b>{total_users}</b>",
        f"  Сегодня:   <b>+{new_today}</b>",
        f"  За неделю: <b>+{new_week}</b>\n",

        "🖥️ <b>Серверы:</b>",
        f"  Активных:  <b>{active_vps}</b>",
        f"  Истекают ≤3д: <b>{expiring_vps}</b>",
        f"  Платежей:  <b>{total_paid}</b>\n",

        "\n".join(chart_rows),
        "",
        "\n".join(tariff_lines),
    ]

    return "\n".join(lines)
