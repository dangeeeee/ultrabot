"""add referrals and user_balances

Revision ID: 0002_referral
Revises: 0001_initial
Create Date: 2025-01-02 00:00:00.000000
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0002_referral"
down_revision: Union[str, None] = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("referrer_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id"), nullable=False),
        sa.Column("referred_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id"), nullable=False, unique=True),
        sa.Column("bonus_paid", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("bonus_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("bonus_currency", sa.String(8), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_referrals_referrer_id", "referrals", ["referrer_id"])

    op.create_table(
        "user_balances",
        sa.Column("telegram_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id"), primary_key=True),
        sa.Column("balance_rub", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("balance_usdt", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_balances")
    op.drop_table("referrals")
