"""
Автоматический бекап PostgreSQL.

Каждые сутки в AUTO_BACKUP_HOUR (UTC) делает pg_dump
и отправляет .sql.gz файл всем администраторам в Telegram.
Также сохраняет копию в data/backups/.
"""
from __future__ import annotations
import asyncio
import gzip
import logging
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from aiogram import Bot
from aiogram.types import BufferedInputFile
from app.core.config import settings

logger = logging.getLogger(__name__)


async def make_backup(bot: Bot) -> None:
    """Создать дамп и отправить администраторам."""
    if not settings.AUTO_BACKUP_ENABLED:
        return

    logger.info("Starting scheduled database backup...")
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"vpsbot_backup_{timestamp}.sql.gz"
    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / filename

    try:
        # Запускаем pg_dump
        env = os.environ.copy()
        env["PGPASSWORD"] = settings.POSTGRES_PASSWORD

        proc = await asyncio.create_subprocess_exec(
            "pg_dump",
            "-h", settings.POSTGRES_HOST,
            "-p", str(settings.POSTGRES_PORT),
            "-U", settings.POSTGRES_USER,
            "-d", settings.POSTGRES_DB,
            "--no-password",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {stderr.decode()}")

        # Сжимаем
        with gzip.open(backup_path, "wb") as f:
            f.write(stdout)

        size_kb = backup_path.stat().st_size // 1024
        logger.info(f"Backup created: {backup_path} ({size_kb} KB)")

        # Отправляем администраторам
        with open(backup_path, "rb") as f:
            file_data = f.read()

        caption = (
            f"🗄️ <b>Автобекап базы данных</b>\n\n"
            f"📅 {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC\n"
            f"📦 Размер: {size_kb} KB\n"
            f"🗃️ База: {settings.POSTGRES_DB}"
        )

        for admin_id in settings.ADMIN_IDS:
            try:
                await bot.send_document(
                    admin_id,
                    BufferedInputFile(file_data, filename=filename),
                    caption=caption,
                )
            except Exception as e:
                logger.warning(f"Failed to send backup to admin {admin_id}: {e}")

        # Удаляем старые бекапы (оставляем последние 7)
        _cleanup_old_backups(backup_dir, keep=7)

    except Exception as e:
        logger.error(f"Backup failed: {e}")
        for admin_id in settings.ADMIN_IDS:
            try:
                await bot.send_message(admin_id, f"❌ <b>Бекап не удался</b>\n<code>{e}</code>")
            except Exception:
                pass


def _cleanup_old_backups(backup_dir: Path, keep: int = 7) -> None:
    backups = sorted(backup_dir.glob("vpsbot_backup_*.sql.gz"), key=lambda p: p.stat().st_mtime)
    for old in backups[:-keep]:
        old.unlink()
        logger.info(f"Deleted old backup: {old.name}")
