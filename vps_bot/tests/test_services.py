"""
Тесты для реферальной системы.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.referral import ReferralRepository


@pytest.mark.asyncio
async def test_cannot_refer_yourself():
    """Нельзя пригласить самого себя."""
    session = AsyncMock()
    repo = ReferralRepository(session)

    result = await repo.register_referral(referrer_id=123, referred_id=123)
    assert result is False


@pytest.mark.asyncio
async def test_referral_bonus_paid_only_once():
    """Реферальный бонус выплачивается только за первую покупку."""
    mock_ref = MagicMock()
    mock_ref.bonus_paid = True  # уже выплачен

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(
        scalar_one_or_none=MagicMock(return_value=mock_ref)
    ))

    from app.services.referral import ReferralRepository
    repo = ReferralRepository(session)
    await repo.mark_bonus_paid(456, 50.0, "RUB")

    # commit не должен вызываться — бонус уже выплачен
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_n8n_notify_skips_if_no_url():
    """n8n уведомление пропускается если URL не настроен."""
    with patch("app.services.n8n.settings") as mock_settings:
        mock_settings.N8N_WEBHOOK_URL = ""
        from app.services.n8n import n8n_notify
        # Не должен падать
        await n8n_notify("test.event", {"key": "value"})


@pytest.mark.asyncio
async def test_ping_format_result_reachable():
    """Форматирование результата ping для доступного хоста."""
    from app.handlers.client.ping import _format_ping_result

    result = {
        "reachable": True,
        "loss_pct": 0,
        "rtt_min": 1.2,
        "rtt_avg": 1.5,
        "rtt_max": 1.8,
        "rtt_mdev": 0.1,
    }
    text = _format_ping_result("1.2.3.4", result)

    assert "1.2.3.4" in text
    assert "1.5" in text
    assert "0%" in text


@pytest.mark.asyncio
async def test_ping_format_result_unreachable():
    """Форматирование результата ping для недоступного хоста."""
    from app.handlers.client.ping import _format_ping_result

    result = {"reachable": False, "loss_pct": 100}
    text = _format_ping_result("1.2.3.4", result)

    assert "недоступен" in text.lower() or "unavailable" in text.lower() or "🔴" in text


@pytest.mark.asyncio
async def test_stats_format_contains_sections():
    """format_stats_text содержит все нужные секции."""
    from app.services.stats import format_stats_text

    stats = {
        "users": {"total": 100, "new_7d": 5, "new_30d": 20},
        "vps": {"active": 42, "total_ever": 100},
        "revenue": {"total": 15000.0, "7d": 2000.0, "30d": 8000.0, "paid_count": 90},
        "daily_revenue": [
            {"date": "2025-01-01", "total": 500.0, "count": 3},
            {"date": "2025-01-02", "total": 800.0, "count": 5},
        ],
        "tariff_stats": [
            {"tariff_id": "starter", "name": "⚡ Старт", "count": 50},
            {"tariff_id": "pro", "name": "💎 Про", "count": 20},
        ],
        "ip_pool": {"total": 20, "free": 15, "used": 5},
    }

    text = format_stats_text(stats)

    assert "Пользователи" in text
    assert "Выручка" in text
    assert "IP пул" in text
    assert "100" in text   # total users
    assert "42" in text    # active VPS
