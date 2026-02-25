import asyncio
import logging
import sys

from app.core.bot import create_bot, create_dispatcher
from app.core.config import settings
from app.core.database import init_db
from app.core.redis import init_redis
from app.core.logger import setup_logging
from app.core.webhook import start_webhook
from app.core.scheduler import start_scheduler
from app.core.startup import run_startup_checks
from app.core.errors import setup_error_handlers


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("🚀 Starting VPS Shop Bot...")
    logger.info(f"Mode: {settings.BOT_RUN_MODE}")

    bot = create_bot()
    dp = create_dispatcher()

    await init_db()
    await init_redis()
    await run_startup_checks()
    setup_error_handlers(dp, bot)
    await start_scheduler(bot)

    if settings.BOT_RUN_MODE == "webhook":
        await start_webhook(bot, dp)
    elif settings.BOT_RUN_MODE == "polling":
        logger.info("Starting polling...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    else:
        raise ValueError(f"Unknown BOT_RUN_MODE: {settings.BOT_RUN_MODE}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
