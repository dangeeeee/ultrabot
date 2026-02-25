"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("full_name", sa.String(128), nullable=True),
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    # ip_pool
    op.create_table(
        "ip_pool",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ip", sa.String(45), nullable=False, unique=True),
        sa.Column("in_use", sa.Boolean(), nullable=False, server_default="false"),
    )

    # vps statuses
    vps_status = sa.Enum("pending", "active", "suspended", "deleted", name="vpsstatus")
    vps_status.create(op.get_bind())

    # vps
    op.create_table(
        "vps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id"), nullable=False),
        sa.Column("vmid", sa.Integer(), nullable=False, unique=True),
        sa.Column("hostname", sa.String(128), nullable=False),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("password", sa.String(64), nullable=False),
        sa.Column("tariff", sa.String(32), nullable=False),
        sa.Column("status", vps_status, nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("reminded_3d", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reminded_1d", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_vps_telegram_id", "vps", ["telegram_id"])

    # payment statuses & providers
    pay_status = sa.Enum("pending", "paid", "failed", "refunded", name="paymentstatus")
    pay_status.create(op.get_bind())
    pay_provider = sa.Enum("cryptobot", "yukassa", name="paymentprovider")
    pay_provider.create(op.get_bind())

    # payments
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id"), nullable=False),
        sa.Column("external_id", sa.String(256), nullable=False, unique=True),
        sa.Column("provider", pay_provider, nullable=False),
        sa.Column("tariff", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("status", pay_status, nullable=False, server_default="pending"),
        sa.Column("renew_vps_id", sa.Integer(), sa.ForeignKey("vps.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_payments_telegram_id", "payments", ["telegram_id"])
    op.create_index("ix_payments_external_id", "payments", ["external_id"])


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("vps")
    op.drop_table("ip_pool")
    op.drop_table("users")
    sa.Enum(name="paymentstatus").drop(op.get_bind())
    sa.Enum(name="paymentprovider").drop(op.get_bind())
    sa.Enum(name="vpsstatus").drop(op.get_bind())
