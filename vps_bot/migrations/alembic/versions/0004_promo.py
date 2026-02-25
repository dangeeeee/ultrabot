"""add promo codes

Revision ID: 0004_promo
Revises: 0003_autorenew
Create Date: 2025-01-04 00:00:00.000000
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0004_promo"
down_revision: Union[str, None] = "0003_autorenew"
branch_labels = None
depends_on = None


def upgrade() -> None:
    promo_type = sa.Enum("percent", "fixed_rub", "fixed_usdt", name="promotype")
    promo_type.create(op.get_bind())

    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("promo_type", promo_type, nullable=False),
        sa.Column("value", sa.Numeric(10, 2), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uses_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("only_tariffs", sa.String(256), nullable=False, server_default=""),
        sa.Column("one_per_user", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_promo_codes_code", "promo_codes", ["code"])

    op.create_table(
        "promo_usages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("promo_id", sa.Integer(), sa.ForeignKey("promo_codes.id"), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id"), nullable=False),
        sa.Column("tariff", sa.String(32), nullable=False),
        sa.Column("discount_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_promo_usages_promo_id", "promo_usages", ["promo_id"])
    op.create_index("ix_promo_usages_telegram_id", "promo_usages", ["telegram_id"])


def downgrade() -> None:
    op.drop_table("promo_usages")
    op.drop_table("promo_codes")
    sa.Enum(name="promotype").drop(op.get_bind())
