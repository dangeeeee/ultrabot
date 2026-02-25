from __future__ import annotations
from typing import Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Telegram ──────────────────────────────────────────────
    BOT_TOKEN: str
    ADMIN_IDS: list[int] = Field(default_factory=list)
    BOT_RUN_MODE: Literal["polling", "webhook"] = "polling"

    # ── Webhook ───────────────────────────────────────────────
    WEBHOOK_URL: str = ""
    WEBHOOK_PATH: str = "/webhook"
    WEBHOOK_SECRET_TOKEN: str = ""
    WEBHOOK_HOST: str = "0.0.0.0"
    WEBHOOK_PORT: int = 8080

    # ── Database ──────────────────────────────────────────────
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "vpsbot"
    POSTGRES_USER: str = "vpsbot"
    POSTGRES_PASSWORD: str = "changeme"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ── Redis ─────────────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"

    # ── Proxmox ───────────────────────────────────────────────
    PROXMOX_HOST: str = ""
    PROXMOX_USER: str = "root@pam"
    PROXMOX_TOKEN_NAME: str = "bot"
    PROXMOX_TOKEN_VALUE: str = ""
    PROXMOX_NODE: str = "pve"
    PROXMOX_STORAGE: str = "local-lvm"
    PROXMOX_BRIDGE: str = "vmbr0"
    PROXMOX_GATEWAY: str = ""
    PROXMOX_TEMPLATE: str = "local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst"
    PROXMOX_IP_POOL: list[str] = Field(default_factory=list)

    # ── Payments: CryptoBot ───────────────────────────────────
    CRYPTOBOT_ENABLED: bool = False
    CRYPTOBOT_TOKEN: str = ""
    CRYPTOBOT_WEBHOOK_PATH: str = "/cryptobot-webhook"

    # ── Payments: YooKassa ────────────────────────────────────
    YUKASSA_ENABLED: bool = False
    YUKASSA_SHOP_ID: str = ""
    YUKASSA_SECRET_KEY: str = ""
    YUKASSA_WEBHOOK_PATH: str = "/yukassa-webhook"

    # ── n8n ───────────────────────────────────────────────────
    N8N_WEBHOOK_URL: str = ""
    N8N_API_KEY: str = ""

    # ── Security ──────────────────────────────────────────────
    API_SECRET_TOKEN: str = ""
    RATE_LIMIT_MESSAGES: int = 30
    RATE_LIMIT_PAYMENTS: int = 5

    # ── Antifrod ──────────────────────────────────────────────
    MAX_VPS_PER_USER: int = 5
    MIN_ACCOUNT_AGE_DAYS: int = 0

    # ── Referral ──────────────────────────────────────────────
    REFERRAL_ENABLED: bool = True
    REFERRAL_BONUS_RUB: float = 50.0
    REFERRAL_BONUS_USDT: float = 0.5

    # ── Notifications ─────────────────────────────────────────
    NOTIFY_CHANNEL_ID: int | None = None
    NOTIFY_TOPIC_ID: int | None = None

    # ── Backup ────────────────────────────────────────────────
    AUTO_BACKUP_ENABLED: bool = False
    AUTO_BACKUP_HOUR: int = 3

    # ── Logs ──────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_ROTATION_ENABLED: bool = True
    LOG_MAX_SIZE_MB: int = 100
    LOG_MAX_FILES: int = 10

    # ── App ───────────────────────────────────────────────────
    TZ: str = "Europe/Moscow"
    SUPPORT_USERNAME: str = "@support"

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @field_validator("PROXMOX_IP_POOL", mode="before")
    @classmethod
    def parse_ip_pool(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v


settings = Settings()

# ── Tariffs ───────────────────────────────────────────────────
TARIFFS: dict[str, dict] = {
    "starter": {
        "name": "⚡ Старт",
        "cpu": 1,
        "ram": 1024,
        "disk": 20,
        "price_rub": 250,
        "price_usdt": 3.0,
        "description": "1 vCPU • 1 GB RAM • 20 GB SSD\nИдеально для VPN, ботов, сайтов",
        "emoji": "⚡",
    },
    "standard": {
        "name": "🚀 Стандарт",
        "cpu": 2,
        "ram": 2048,
        "disk": 40,
        "price_rub": 450,
        "price_usdt": 5.0,
        "description": "2 vCPU • 2 GB RAM • 40 GB SSD\nДля проектов со средней нагрузкой",
        "emoji": "🚀",
    },
    "pro": {
        "name": "💎 Про",
        "cpu": 4,
        "ram": 4096,
        "disk": 80,
        "price_rub": 850,
        "price_usdt": 10.0,
        "description": "4 vCPU • 4 GB RAM • 80 GB SSD\nДля высоконагруженных проектов",
        "emoji": "💎",
    },
}
