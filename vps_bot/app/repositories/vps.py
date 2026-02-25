"""
Репозиторий для работы с VPS.

VpsRepository — все операции с таблицей vps и ip_pool.
"""
from __future__ import annotations

import logging
from datetime import datetime
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Vps, VpsStatus, IpPool

logger = logging.getLogger(__name__)


class VpsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Создание ──────────────────────────────────────────

    async def create(
        self,
        telegram_id: int,
        vmid: int,
        hostname: str,
        ip: str,
        password: str,
        tariff: str,
        expires_at: datetime,
    ) -> Vps:
        vps = Vps(
            telegram_id=telegram_id,
            vmid=vmid,
            hostname=hostname,
            ip=ip,
            password=password,
            tariff=tariff,
            expires_at=expires_at,
            status=VpsStatus.ACTIVE,
        )
        self.session.add(vps)
        await self.session.commit()
        await self.session.refresh(vps)
        return vps

    # ── Получение ─────────────────────────────────────────

    async def get_by_id(self, vps_id: int) -> Vps | None:
        return await self.session.get(Vps, vps_id)

    async def get_by_ip(self, ip: str) -> Vps | None:
        result = await self.session.execute(
            select(Vps).where(Vps.ip == ip)
        )
        return result.scalar_one_or_none()

    async def get_user_vps(self, telegram_id: int) -> list[Vps]:
        """Активные VPS пользователя (не удалённые)."""
        result = await self.session.execute(
            select(Vps)
            .where(Vps.telegram_id == telegram_id)
            .where(Vps.status != VpsStatus.DELETED)
            .order_by(Vps.created_at.desc())
        )
        return result.scalars().all()

    async def get_all(self, limit: int = 50) -> list[Vps]:
        """Все VPS (не удалённые), сортировка по дате создания."""
        result = await self.session.execute(
            select(Vps)
            .where(Vps.status != VpsStatus.DELETED)
            .order_by(Vps.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_expiring(self, days: int) -> list[Vps]:
        """VPS которые истекают ровно через `days` дней (±12ч)."""
        from datetime import timedelta
        now = datetime.utcnow()
        start = now + timedelta(days=days) - timedelta(hours=12)
        end   = now + timedelta(days=days) + timedelta(hours=12)

        field = Vps.reminded_3d if days == 3 else Vps.reminded_1d

        result = await self.session.execute(
            select(Vps)
            .where(Vps.status == VpsStatus.ACTIVE)
            .where(Vps.expires_at.between(start, end))
            .where(field == False)  # noqa
        )
        return result.scalars().all()

    async def get_expired(self) -> list[Vps]:
        """VPS у которых срок истёк и они ещё активны."""
        result = await self.session.execute(
            select(Vps)
            .where(Vps.status == VpsStatus.ACTIVE)
            .where(Vps.expires_at < datetime.utcnow())
        )
        return result.scalars().all()

    # ── Изменение ─────────────────────────────────────────

    async def extend(self, vps_id: int, new_expires_at: datetime) -> None:
        """Продлить VPS — обновить дату истечения."""
        vps = await self.session.get(Vps, vps_id)
        if vps:
            vps.expires_at = new_expires_at
            # Сбрасываем флаги напоминаний при продлении
            vps.reminded_3d = False
            vps.reminded_1d = False
            await self.session.commit()

    async def mark_reminded(self, vps_id: int, days: int) -> None:
        vps = await self.session.get(Vps, vps_id)
        if vps:
            if days == 3:
                vps.reminded_3d = True
            elif days == 1:
                vps.reminded_1d = True
            await self.session.commit()

    async def mark_deleted(self, vps_id: int) -> None:
        vps = await self.session.get(Vps, vps_id)
        if vps:
            vps.status = VpsStatus.DELETED
            await self.session.commit()

    # ── IP пул ────────────────────────────────────────────

    async def acquire_ip(self) -> str | None:
        """
        Атомарно захватить свободный IP из пула.
        Возвращает IP-строку или None если пул исчерпан.
        """
        result = await self.session.execute(
            select(IpPool)
            .where(IpPool.in_use == False)  # noqa
            .limit(1)
            .with_for_update(skip_locked=True)   # конкурентная безопасность
        )
        ip_row = result.scalar_one_or_none()
        if not ip_row:
            return None
        ip_row.in_use = True
        await self.session.commit()
        return ip_row.ip

    async def release_ip(self, ip: str) -> None:
        """Вернуть IP в пул."""
        result = await self.session.execute(
            select(IpPool).where(IpPool.ip == ip)
        )
        ip_row = result.scalar_one_or_none()
        if ip_row:
            ip_row.in_use = False
            await self.session.commit()
