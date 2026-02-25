from __future__ import annotations
import logging
import secrets
import string
import asyncio
import aiohttp
from app.core.config import settings

logger = logging.getLogger(__name__)


def generate_password(length: int = 18) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(chars) for _ in range(length))


class ProxmoxService:
    def __init__(self) -> None:
        self._base = settings.PROXMOX_HOST.rstrip("/")
        self._node = settings.PROXMOX_NODE
        self._headers = {
            "Authorization": (
                f"PVEAPIToken={settings.PROXMOX_USER}"
                f"!{settings.PROXMOX_TOKEN_NAME}={settings.PROXMOX_TOKEN_VALUE}"
            )
        }

    async def _req(self, method: str, path: str, json: dict | None = None) -> dict:
        url = f"{self._base}/api2/json{path}"
        async with aiohttp.ClientSession() as s:
            async with s.request(method, url, headers=self._headers, json=json, ssl=False) as resp:
                data = await resp.json()
                if resp.status not in (200, 201):
                    raise RuntimeError(f"Proxmox {method} {path} → {resp.status}: {data}")
                return data.get("data", {})

    async def next_vmid(self) -> int:
        data = await self._req("GET", "/cluster/nextid")
        return int(data)

    async def create_lxc(self, vmid: int, hostname: str, ip: str, password: str, tariff: dict) -> None:
        payload = {
            "vmid": vmid,
            "hostname": hostname,
            "ostemplate": settings.PROXMOX_TEMPLATE,
            "memory": tariff["ram"],
            "cores": tariff["cpu"],
            "rootfs": f"{settings.PROXMOX_STORAGE}:{tariff['disk']}",
            "net0": f"name=eth0,bridge={settings.PROXMOX_BRIDGE},ip={ip}/32,gw={settings.PROXMOX_GATEWAY}",
            "password": password,
            "start": 1,
            "unprivileged": 1,
            "features": "nesting=1",
            "nameserver": "8.8.8.8 1.1.1.1",
        }
        await self._req("POST", f"/nodes/{self._node}/lxc", payload)
        await asyncio.sleep(5)  # ждём пока контейнер поднимется
        logger.info(f"✅ LXC {vmid} ({hostname} / {ip}) created")

    async def delete_lxc(self, vmid: int) -> None:
        try:
            await self._req("POST", f"/nodes/{self._node}/lxc/{vmid}/status/stop")
            await asyncio.sleep(3)
        except Exception:
            pass
        await self._req("DELETE", f"/nodes/{self._node}/lxc/{vmid}")
        logger.info(f"🗑️ LXC {vmid} deleted")

    async def reboot_lxc(self, vmid: int) -> None:
        await self._req("POST", f"/nodes/{self._node}/lxc/{vmid}/status/reboot")

    async def start_lxc(self, vmid: int) -> None:
        await self._req("POST", f"/nodes/{self._node}/lxc/{vmid}/status/start")

    async def stop_lxc(self, vmid: int) -> None:
        await self._req("POST", f"/nodes/{self._node}/lxc/{vmid}/status/stop")

    async def status_lxc(self, vmid: int) -> dict:
        data = await self._req("GET", f"/nodes/{self._node}/lxc/{vmid}/status/current")
        return {
            "running": data.get("status") == "running",
            "status": data.get("status", "unknown"),
            "cpu_pct": round(data.get("cpu", 0) * 100, 1),
            "mem_used_mb": data.get("mem", 0) // 1024 // 1024,
            "mem_total_mb": data.get("maxmem", 0) // 1024 // 1024,
            "uptime_sec": data.get("uptime", 0),
        }

    async def node_status(self) -> dict:
        data = await self._req("GET", f"/nodes/{self._node}/status")
        return {
            "cpu_pct": round(data.get("cpu", 0) * 100, 1),
            "mem_used_gb": data.get("memory", {}).get("used", 0) // 1024 ** 3,
            "mem_total_gb": data.get("memory", {}).get("total", 0) // 1024 ** 3,
        }


proxmox_service = ProxmoxService()
