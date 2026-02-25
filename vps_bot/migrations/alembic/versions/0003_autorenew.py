"""add vps_autorenew

Revision ID: 0003_autorenew
Revises: 0002_referral
Create Date: 2025-01-03 00:00:00.000000
"""
from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = "0003_autorenew"
down_revision: Union[str, None] = "0002_referral"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vps_autorenew",
        sa.Column("vps_id", sa.Integer(), sa.ForeignKey("vps.id"), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("preferred_provider", sa.String(20), nullable=False, server_default="cryptobot"),
        sa.Column("last_attempted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_vps_autorenew_telegram_id", "vps_autorenew", ["telegram_id"])


def downgrade() -> None:
    op.drop_table("vps_autorenew")
