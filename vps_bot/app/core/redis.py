import logging
from redis.asyncio import Redis, from_url
from app.core.config import settings

logger = logging.getLogger(__name__)
redis: Redis | None = None


async def init_redis() -> None:
    global redis
    redis = from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    await redis.ping()
    logger.info("✅ Redis connected")


async def get_redis() -> Redis:
    return redis
