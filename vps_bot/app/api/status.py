"""
Публичная HTML страница статуса: GET /status
Показывает состояние всех сервисов в красивом виде.
Не требует авторизации — полезно для мониторинга и клиентов.
"""
from __future__ import annotations
import time
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from app.core.config import settings

router = APIRouter()

_START_TIME = time.time()


@router.get("/status", response_class=HTMLResponse)
async def status_page() -> HTMLResponse:
    checks = await _run_checks()
    overall = "operational" if all(c["ok"] for c in checks) else "degraded"
    uptime_sec = int(time.time() - _START_TIME)
    uptime_str = _fmt_uptime(uptime_sec)

    html = _render_html(checks, overall, uptime_str)
    return HTMLResponse(content=html)


async def _run_checks() -> list[dict]:
    checks = []

    # Bot
    checks.append({"name": "Telegram Bot", "ok": True, "detail": "Running"})

    # PostgreSQL
    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as s:
            await s.execute(text("SELECT 1"))
        checks.append({"name": "PostgreSQL", "ok": True, "detail": "Connected"})
    except Exception as e:
        checks.append({"name": "PostgreSQL", "ok": False, "detail": str(e)[:60]})

    # Redis
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        await r.ping()
        checks.append({"name": "Redis", "ok": True, "detail": "Connected"})
    except Exception as e:
        checks.append({"name": "Redis", "ok": False, "detail": str(e)[:60]})

    # Proxmox
    if settings.PROXMOX_HOST:
        try:
            from app.services.proxmox import proxmox_service
            st = await proxmox_service.node_status()
            checks.append({
                "name": "Proxmox",
                "ok": True,
                "detail": f"CPU {st['cpu_pct']}% · RAM {st['mem_used_gb']}/{st['mem_total_gb']} GB",
            })
        except Exception as e:
            checks.append({"name": "Proxmox", "ok": False, "detail": str(e)[:60]})

    # n8n
    if settings.N8N_WEBHOOK_URL:
        checks.append({"name": "n8n", "ok": True, "detail": "Configured"})

    return checks


def _fmt_uptime(sec: int) -> str:
    h, m = divmod(sec // 60, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}д {h}ч {m}м"
    if h:
        return f"{h}ч {m}м"
    return f"{m}м"


def _render_html(checks: list[dict], overall: str, uptime: str) -> str:
    overall_color = "#22c55e" if overall == "operational" else "#f59e0b"
    overall_label = "Все системы работают" if overall == "operational" else "Частичный сбой"
    now = datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")

    rows = ""
    for c in checks:
        icon = "✅" if c["ok"] else "❌"
        status_text = "Работает" if c["ok"] else "Недоступен"
        badge_color = "#22c55e" if c["ok"] else "#ef4444"
        rows += f"""
        <div class="service-row">
            <div class="service-name">{icon} {c['name']}</div>
            <div class="service-detail">{c.get('detail', '')}</div>
            <div class="badge" style="background:{badge_color}">{status_text}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>VPS Shop — Статус</title>
  <meta http-equiv="refresh" content="60">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0f172a; color: #e2e8f0; min-height: 100vh;
      display: flex; align-items: center; justify-content: center; padding: 20px;
    }}
    .card {{
      background: #1e293b; border-radius: 16px; padding: 40px;
      max-width: 600px; width: 100%; box-shadow: 0 25px 50px rgba(0,0,0,.5);
    }}
    .header {{ text-align: center; margin-bottom: 32px; }}
    .header h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 8px; }}
    .overall-badge {{
      display: inline-block; padding: 8px 20px; border-radius: 20px;
      font-weight: 600; font-size: 15px; color: #fff;
      background: {overall_color}; margin-bottom: 8px;
    }}
    .subtitle {{ color: #64748b; font-size: 13px; }}
    .services {{ margin-bottom: 24px; }}
    .service-row {{
      display: flex; align-items: center; gap: 12px;
      padding: 14px 0; border-bottom: 1px solid #334155;
    }}
    .service-row:last-child {{ border-bottom: none; }}
    .service-name {{ font-weight: 600; min-width: 140px; }}
    .service-detail {{ flex: 1; color: #94a3b8; font-size: 13px; }}
    .badge {{
      padding: 4px 12px; border-radius: 12px; font-size: 12px;
      font-weight: 600; color: #fff; white-space: nowrap;
    }}
    .footer {{ text-align: center; color: #475569; font-size: 12px; }}
    .uptime {{ color: #22c55e; font-weight: 600; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1>🖥️ VPS Shop</h1>
      <div class="overall-badge">{overall_label}</div>
      <div class="subtitle">Последнее обновление: {now}</div>
    </div>
    <div class="services">{rows}
    </div>
    <div class="footer">
      Uptime: <span class="uptime">{uptime}</span> &nbsp;·&nbsp; Обновляется каждые 60 сек
    </div>
  </div>
</body>
</html>"""
