from __future__ import annotations
import enum
from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, ForeignKey,
    Integer, Numeric, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class VpsStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentProvider(str, enum.Enum):
    CRYPTOBOT = "cryptobot"
    YUKASSA = "yukassa"


# ── User ──────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str | None] = mapped_column(String(128))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    vps_list: Mapped[list[Vps]] = relationship("Vps", back_populates="user", lazy="select")
    payments: Mapped[list[Payment]] = relationship("Payment", back_populates="user", lazy="select")


# ── VPS ───────────────────────────────────────────────────────

class Vps(Base):
    __tablename__ = "vps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    vmid: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    hostname: Mapped[str] = mapped_column(String(128), nullable=False)
    ip: Mapped[str] = mapped_column(String(45), nullable=False)
    password: Mapped[str] = mapped_column(String(64), nullable=False)
    tariff: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[VpsStatus] = mapped_column(Enum(VpsStatus), default=VpsStatus.ACTIVE)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reminded_3d: Mapped[bool] = mapped_column(Boolean, default=False)
    reminded_1d: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship("User", back_populates="vps_list")


# ── Payment ───────────────────────────────────────────────────

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    provider: Mapped[PaymentProvider] = mapped_column(Enum(PaymentProvider), nullable=False)
    tariff: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    renew_vps_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("vps.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship("User", back_populates="payments")


# ── IP Pool ───────────────────────────────────────────────────

class IpPool(Base):
    __tablename__ = "ip_pool"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(String(45), unique=True, nullable=False)
    in_use: Mapped[bool] = mapped_column(Boolean, default=False)


# ── Lazy imports для регистрации всех моделей в Alembic ───────
def _import_all() -> None:
    from app.services.referral import Referral, UserBalance  # noqa
