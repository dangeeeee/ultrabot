"""
Health check эндпоинты.

GET /health            — быстрая проверка (используется Docker healthcheck)
GET /health/detailed   — детальная проверка с проверкой БД и Redis
"""
from __future__ import annotations
import time
from fastapi import APIRouter, Header, HTTPException

router = APIRouter()
_START = time.time()


@router.get("/health")
async def health_simple() -> dict:
    """Быстрый healthcheck — всегда 200 если процесс жив."""
    return {"ok": True, "uptime": int(time.time() - _START)}


@router.get("/health/detailed")
async def health_detailed(
    x_api_key: str = Header(default=""),
) -> dict:
    """
    Детальный healthcheck.
    Требует заголовок X-Api-Key равный API_SECRET_TOKEN из .env.
    """
    from app.core.config import settings
    if settings.API_SECRET_TOKEN and x_api_key != settings.API_SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    result: dict = {"ok": True, "uptime": int(time.time() - _START), "checks": {}}

    # PostgreSQL
    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as s:
            await s.execute(text("SELECT 1"))
        result["checks"]["postgres"] = "ok"
    except Exception as e:
        result["checks"]["postgres"] = f"error: {e}"
        result["ok"] = False

    # Redis
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        await r.ping()
        result["checks"]["redis"] = "ok"
    except Exception as e:
        result["checks"]["redis"] = f"error: {e}"
        result["ok"] = False

    return result
