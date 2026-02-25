"""
Реферальная система.

Флоу:
  Пользователь A делится ссылкой /start?ref=<telegram_id_A>
  Пользователь B кликает → регистрируется с referrer_id=A
  Когда B совершает первую оплату → A получает бонус на баланс

Бонусы настраиваются в .env:
  REFERRAL_ENABLED=true
  REFERRAL_BONUS_RUB=50        # рублей на баланс A за каждого оплатившего реферала
  REFERRAL_BONUS_USDT=0.5      # USDT бонус (если платёж в USDT)
"""
from __future__ import annotations
import logging
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, func, select
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import Base

logger = logging.getLogger(__name__)


# ── Model ─────────────────────────────────────────────────────

class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    referred_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, unique=True)
    bonus_paid: Mapped[bool] = mapped_column(Boolean, default=False)          # получил ли реферер бонус
    bonus_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    bonus_currency: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserBalance(Base):
    """Бонусный баланс пользователя (накапливается от рефералов)."""
    __tablename__ = "user_balances"

    telegram_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), primary_key=True)
    balance_rub: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    balance_usdt: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# ── Repository ────────────────────────────────────────────────

class ReferralRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def register_referral(self, referrer_id: int, referred_id: int) -> bool:
        """Зарегистрировать реферала. Вернуть True если добавлен новый."""
        existing = await self.session.execute(
            select(Referral).where(Referral.referred_id == referred_id)
        )
        if existing.scalar_one_or_none():
            return False  # уже зарегистрирован
        if referrer_id == referred_id:
            return False  # нельзя рефереть самого себя

        ref = Referral(referrer_id=referrer_id, referred_id=referred_id)
        self.session.add(ref)
        await self.session.commit()
        logger.info(f"Referral registered: {referrer_id} → {referred_id}")
        return True

    async def get_referrer(self, referred_id: int) -> int | None:
        result = await self.session.execute(
            select(Referral.referrer_id).where(Referral.referred_id == referred_id)
        )
        row = result.scalar_one_or_none()
        return row

    async def mark_bonus_paid(self, referred_id: int, amount: float, currency: str) -> None:
        result = await self.session.execute(
            select(Referral).where(Referral.referred_id == referred_id)
        )
        ref = result.scalar_one_or_none()
        if ref and not ref.bonus_paid:
            ref.bonus_paid = True
            ref.bonus_amount = amount
            ref.bonus_currency = currency
            ref.paid_at = datetime.utcnow()
            await self.session.commit()

    async def count_referrals(self, referrer_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Referral.id)).where(Referral.referrer_id == referrer_id)
        )
        return result.scalar_one()

    async def count_paid_referrals(self, referrer_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Referral.id))
            .where(Referral.referrer_id == referrer_id)
            .where(Referral.bonus_paid == True)  # noqa
        )
        return result.scalar_one()

    async def get_or_create_balance(self, telegram_id: int) -> UserBalance:
        result = await self.session.execute(
            select(UserBalance).where(UserBalance.telegram_id == telegram_id)
        )
        balance = result.scalar_one_or_none()
        if not balance:
            balance = UserBalance(telegram_id=telegram_id)
            self.session.add(balance)
            await self.session.commit()
            await self.session.refresh(balance)
        return balance

    async def add_balance(self, telegram_id: int, rub: float = 0, usdt: float = 0) -> UserBalance:
        balance = await self.get_or_create_balance(telegram_id)
        balance.balance_rub = float(balance.balance_rub) + rub
        balance.balance_usdt = float(balance.balance_usdt) + usdt
        await self.session.commit()
        await self.session.refresh(balance)
        return balance
