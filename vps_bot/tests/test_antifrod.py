"""
Тесты для антифрод сервиса.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_check_vps_limit_passes_under_limit():
    """Пользователь с 2 VPS при лимите 5 — должен пройти."""
    mock_vps_list = [MagicMock(), MagicMock()]  # 2 VPS

    with patch("app.services.antifrod.settings") as mock_settings, \
         patch("app.services.antifrod.AsyncSessionLocal") as mock_session_cls, \
         patch("app.services.antifrod.VpsRepository") as mock_repo_cls:

        mock_settings.MAX_VPS_PER_USER = 5
        mock_repo = AsyncMock()
        mock_repo.get_user_vps = AsyncMock(return_value=mock_vps_list)
        mock_repo_cls.return_value = mock_repo

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        from app.services.antifrod import check_vps_limit
        # Не должен бросить исключение
        await check_vps_limit(123456)


@pytest.mark.asyncio
async def test_check_vps_limit_fails_at_limit():
    """Пользователь с 5 VPS при лимите 5 — должен получить ошибку."""
    mock_vps_list = [MagicMock()] * 5

    with patch("app.services.antifrod.settings") as mock_settings, \
         patch("app.services.antifrod.AsyncSessionLocal") as mock_session_cls, \
         patch("app.services.antifrod.VpsRepository") as mock_repo_cls:

        mock_settings.MAX_VPS_PER_USER = 5
        mock_repo = AsyncMock()
        mock_repo.get_user_vps = AsyncMock(return_value=mock_vps_list)
        mock_repo_cls.return_value = mock_repo

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        from app.services.antifrod import check_vps_limit, AntifrodError
        with pytest.raises(AntifrodError) as exc_info:
            await check_vps_limit(123456)

        assert "лимит" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_duplicate_payment_blocked():
    """Второй вызов с тем же invoice_id должен быть заблокирован."""
    mock_redis = AsyncMock()
    # Первый вызов — SET NX возвращает True (успех)
    # Второй вызов — SET NX возвращает None (уже занято)
    mock_redis.set = AsyncMock(side_effect=[True, None])

    with patch("app.services.antifrod.get_redis", return_value=mock_redis):
        from app.services.antifrod import check_duplicate_payment, AntifrodError

        # Первый вызов проходит
        await check_duplicate_payment("inv_001")

        # Второй — блокируется
        with pytest.raises(AntifrodError):
            await check_duplicate_payment("inv_001")
