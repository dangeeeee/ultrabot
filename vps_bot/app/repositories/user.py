"""
Репозитории для работы с пользователями и платежами.

UserRepository    — CRUD для таблицы users
PaymentRepository — CRUD для таблицы payments
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Payment, PaymentStatus


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Создание / получение ──────────────────────────────

    async def get_or_create(
        self,
        telegram_id: int,
        username: str | None,
        full_name: str | None,
    ) -> tuple[User, bool]:
        """
        Найти или создать пользователя.
        Возвращает (user, is_new).
        Обновляет username/full_name при изменении.
        """
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if user:
            changed = False
            if user.username != username:
                user.username = username
                changed = True
            if user.full_name != full_name:
                user.full_name = full_name
                changed = True
            if changed:
                await self.session.commit()
            return user, False

        user = User(telegram_id=telegram_id, username=username, full_name=full_name)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user, True

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        """Поиск по username (без @, без учёта регистра)."""
        result = await self.session.execute(
            select(User).where(
                func.lower(User.username) == username.lower()
            )
        )
        return result.scalar_one_or_none()

    # ── Списки ────────────────────────────────────────────

    async def get_all_ids(self) -> list[int]:
        """Все telegram_id активных (не забаненных) пользователей."""
        result = await self.session.execute(
            select(User.telegram_id).where(User.is_banned == False)  # noqa
        )
        return [row[0] for row in result.all()]

    async def get_recent(self, limit: int = 10) -> list[User]:
        """Последние зарегистрированные пользователи."""
        result = await self.session.execute(
            select(User).order_by(User.created_at.desc()).limit(limit)
        )
        return result.scalars().all()

    async def get_banned(self) -> list[User]:
        """Все забаненные пользователи."""
        result = await self.session.execute(
            select(User).where(User.is_banned == True).order_by(User.created_at.desc())  # noqa
        )
        return result.scalars().all()

    # ── Счётчики ──────────────────────────────────────────

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(User.id)))
        return result.scalar_one()

    # ── Изменение ─────────────────────────────────────────

    async def set_banned(self, telegram_id: int, banned: bool) -> None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.is_banned = banned
            await self.session.commit()


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Создание / получение ──────────────────────────────

    async def create(self, **kwargs) -> Payment:
        payment = Payment(**kwargs)
        self.session.add(payment)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def get_by_external_id(self, external_id: str) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(Payment.external_id == external_id)
        )
        return result.scalar_one_or_none()

    # ── Изменение ─────────────────────────────────────────

    async def set_status(self, payment_id: int, status: PaymentStatus) -> None:
        payment = await self.session.get(Payment, payment_id)
        if payment:
            payment.status = status
            await self.session.commit()

    # ── Агрегаты — общие ──────────────────────────────────

    async def total_revenue(self) -> float:
        result = await self.session.execute(
            select(func.sum(Payment.amount)).where(Payment.status == PaymentStatus.PAID)
        )
        return float(result.scalar_one() or 0)

    async def count_paid(self) -> int:
        result = await self.session.execute(
            select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PAID)
        )
        return result.scalar_one()

    # ── Агрегаты — по пользователю ────────────────────────

    async def count_paid_by_user(self, telegram_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Payment.id))
            .where(Payment.telegram_id == telegram_id)
            .where(Payment.status == PaymentStatus.PAID)
        )
        return result.scalar_one()

    async def total_by_user(self, telegram_id: int) -> float:
        result = await self.session.execute(
            select(func.sum(Payment.amount))
            .where(Payment.telegram_id == telegram_id)
            .where(Payment.status == PaymentStatus.PAID)
        )
        return float(result.scalar_one() or 0)

    async def get_recent(self, limit: int = 10) -> list[User]:
        """Последние зарегистрированные пользователи."""
        result = await self.session.execute(
            select(User).order_by(User.created_at.desc()).limit(limit)
        )
        return result.scalars().all()

    async def get_banned(self) -> list[User]:
        """Все заблокированные пользователи."""
        result = await self.session.execute(
            select(User).where(User.is_banned == True).order_by(User.created_at.desc())  # noqa
        )
        return result.scalars().all()

    async def get_by_username(self, username: str) -> User | None:
        """Найти пользователя по username (без @)."""
        result = await self.session.execute(
            select(User).where(User.username == username.lstrip("@"))
        )
        return result.scalar_one_or_none()
