"""
Тесты для Proxmox сервиса.
Используем моки — реального Proxmox нет в тестах.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.proxmox import generate_password


def test_generate_password_length():
    """Пароль должен быть ровно 18 символов."""
    pwd = generate_password()
    assert len(pwd) == 18


def test_generate_password_uniqueness():
    """Два пароля подряд не должны совпадать."""
    p1 = generate_password()
    p2 = generate_password()
    assert p1 != p2


def test_generate_password_contains_allowed_chars():
    """Пароль содержит только разрешённые символы."""
    import string
    allowed = set(string.ascii_letters + string.digits + "!@#$%")
    pwd = generate_password()
    assert all(c in allowed for c in pwd)


@pytest.mark.asyncio
async def test_proxmox_status_parses_response():
    """node_status() корректно разбирает ответ Proxmox API."""
    fake_response = {
        "data": {
            "cpu": 0.42,
            "memory": {"used": 8 * 1024**3, "total": 32 * 1024**3},
        }
    }

    with patch("app.services.proxmox.settings") as mock_settings, \
         patch("aiohttp.ClientSession") as mock_session_cls:

        mock_settings.PROXMOX_HOST = "https://1.2.3.4:8006"
        mock_settings.PROXMOX_NODE = "pve"
        mock_settings.PROXMOX_USER = "root@pam"
        mock_settings.PROXMOX_TOKEN_NAME = "bot"
        mock_settings.PROXMOX_TOKEN_VALUE = "test-token"

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=fake_response)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.request = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        mock_session_cls.return_value = mock_session

        from app.services.proxmox import ProxmoxService
        svc = ProxmoxService()
        result = await svc.node_status()

        assert result["cpu_pct"] == pytest.approx(42.0, abs=0.1)
        assert result["mem_total_gb"] == 32
        assert result["mem_used_gb"] == 8
