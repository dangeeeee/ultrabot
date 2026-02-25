"""
Система промокодов.

Типы скидок:
  - percent  — % скидки от цены (например 20 = -20%)
  - fixed_rub — фиксированная скидка в рублях
  - fixed_usdt — фиксированная скидка в USDT

Ограничения:
  - max_uses: лимит активаций (0 = безлимит)
  - expires_at: дата истечения
  - one_per_user: один раз на пользователя
  - only_tariffs: список тарифов для которых работает (пусто = все)

Команды admin:
  /addpromo CODE PERCENT 20 - скидка 20%
  /addpromo CODE FIXED_RUB 100 --uses 50 --expire 2025-12-31
  /promos — список всех промокодов
  /delpromo CODE — удалить промокод
"""
from __future__ import annotations
import enum
import logging
from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, ForeignKey,
    Integer, Numeric, String, Text, func, select, update
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import Base

logger = logging.getLogger(__name__)


class PromoType(str, enum.Enum):
    PERCENT = "percent"
    FIXED_RUB = "fixed_rub"
    FIXED_USDT = "fixed_usdt"


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    promo_type: Mapped[PromoType] = mapped_column(Enum(PromoType), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=0)     # 0 = безлимит
    uses_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    only_tariffs: Mapped[str] = mapped_column(String(256), default="")  # "starter,standard"
    one_per_user: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PromoUsage(Base):
    __tablename__ = "promo_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promo_id: Mapped[int] = mapped_column(Integer, ForeignKey("promo_codes.id"), nullable=False)
    telegram_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    tariff: Mapped[str] = mapped_column(String(32), nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    used_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PromoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_code(self, code: str) -> PromoCode | None:
        result = await self.session.execute(
            select(PromoCode).where(PromoCode.code == code.upper())
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        code: str,
        promo_type: PromoType,
        value: float,
        created_by: int,
        max_uses: int = 0,
        expires_at: datetime | None = None,
        only_tariffs: str = "",
        one_per_user: bool = True,
    ) -> PromoCode:
        promo = PromoCode(
            code=code.upper(),
            promo_type=promo_type,
            value=value,
            max_uses=max_uses,
            created_by=created_by,
            expires_at=expires_at,
            only_tariffs=only_tariffs,
            one_per_user=one_per_user,
        )
        self.session.add(promo)
        await self.session.commit()
        await self.session.refresh(promo)
        return promo

    async def validate(
        self, code: str, telegram_id: int, tariff_id: str
    ) -> tuple[PromoCode, float, str] | None:
        """
        Проверить промокод. Вернуть (promo, discount_amount, currency) или None.
        Выбрасывает ValueError с описанием ошибки.
        """
        promo = await self.get_by_code(code)
        if not promo:
            raise ValueError("❌ Промокод не найден")

        if not promo.is_active:
            raise ValueError("❌ Промокод недействителен")

        if promo.expires_at and promo.expires_at < datetime.utcnow():
            raise ValueError("❌ Срок действия промокода истёк")

        if promo.max_uses > 0 and promo.uses_count >= promo.max_uses:
            raise ValueError("❌ Промокод использован максимальное количество раз")

        # Проверка тарифа
        if promo.only_tariffs:
            allowed = [t.strip() for t in promo.only_tariffs.split(",")]
            if tariff_id not in allowed:
                raise ValueError(f"❌ Промокод работает только для тарифов: {', '.join(allowed)}")

        # Проверка one_per_user
        if promo.one_per_user:
            used = await self.session.execute(
                select(PromoUsage).where(
                    PromoUsage.promo_id == promo.id,
                    PromoUsage.telegram_id == telegram_id,
                )
            )
            if used.scalar_one_or_none():
                raise ValueError("❌ Ты уже использовал этот промокод")

        from app.core.config import TARIFFS
        t = TARIFFS.get(tariff_id, {})

        if promo.promo_type == PromoType.PERCENT:
            discount_rub = t.get("price_rub", 0) * float(promo.value) / 100
            discount_usdt = t.get("price_usdt", 0) * float(promo.value) / 100
            return promo, discount_rub, "RUB"   # вернём оба через tuple расширенный
        elif promo.promo_type == PromoType.FIXED_RUB:
            return promo, float(promo.value), "RUB"
        elif promo.promo_type == PromoType.FIXED_USDT:
            return promo, float(promo.value), "USDT"

        return None

    async def apply(
        self, promo: PromoCode, telegram_id: int, tariff_id: str,
        discount_amount: float, currency: str
    ) -> None:
        """Зафиксировать использование промокода."""
        usage = PromoUsage(
            promo_id=promo.id,
            telegram_id=telegram_id,
            tariff=tariff_id,
            discount_amount=discount_amount,
            currency=currency,
        )
        self.session.add(usage)
        await self.session.execute(
            update(PromoCode)
            .where(PromoCode.id == promo.id)
            .values(uses_count=PromoCode.uses_count + 1)
        )
        await self.session.commit()

    async def deactivate(self, code: str) -> bool:
        promo = await self.get_by_code(code)
        if not promo:
            return False
        promo.is_active = False
        await self.session.commit()
        return True

    async def list_all(self) -> list[PromoCode]:
        result = await self.session.execute(
            select(PromoCode).order_by(PromoCode.created_at.desc()).limit(50)
        )
        return result.scalars().all()
