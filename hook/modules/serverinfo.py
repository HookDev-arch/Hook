__version__ = (3, 3, 0)

# meta developer: @hookdev_arch
# meta icon: https://example.com/moodmirror_icon.png
# meta banner: https://i.yapx.ru/Yk4OQ.jpg

# requires: psutil

import contextlib
import os
import platform
import sys
import shutil
import psutil
from telethon.tl.types import Message

from .. import loader, utils

def bytes_to_megabytes(b: int) -> int:
    return round(b / 1024 / 1024, 1)

def bytes_to_gigabytes(b: int) -> float:
    return round(b / 1024 / 1024 / 1024, 2)

@loader.tds
class serverInfoMod(loader.Module):
    """Show server info"""

    strings = {
        "name": "ServerInfo",
        "loading": "<emoji document_id=5271897426117009417>🚘</emoji> <b>Loading server info...</b>",
        "servinfo": (
            "<emoji document_id=5271897426117009417>🚘</emoji> <b>Server Info</b>:\n\n"
            "<emoji document_id=5172854840321114816>💻</emoji> <b>CPU:</b> {cpu_name} ({cpu_cores} Cores, {cpu_load}%)\n"
            "<emoji document_id=5174693704799093859>💻</emoji> <b>RAM:</b> {ram_used} / {ram_total}MB ({ram_percent}%) DIMM\n"
            "<emoji document_id=5172854840321114816>💽</emoji> <b>Disk:</b> {disk_used} / {disk_total}GB ({disk_percent}%) {disk_type}\n"
            "<emoji document_id=5172622400986022463>🎮</emoji> <b>GPU:</b> NVIDIA GeForce RTX 4060 Ti\n"
            "🧠 <b>VRAM:</b> 1.4 / 8.0 GB (dedicated), 1.5 / 23.9 GB (shared)\n"
            "📅 <b>Driver:</b> 32.0.15.8088 (27.07.2025)\n"
            "🎮 <b>DirectX:</b> 12 (FL 12.1)\n\n"
            "<emoji document_id=5172474181664637769>💻</emoji> <b>Kernel:</b> {kernel}\n"
            "{arch_emoji} <b>Arch:</b> {arch}\n"
            "<emoji document_id=5172622400986022463>💻</emoji> <b>OS:</b> {os}\n"
            "<emoji document_id=5172839378438849164>💻</emoji> <b>Python:</b> {python}"
        ),
    }

    strings_ru = {
        "loading": "<emoji document_id=5271897426117009417>🚘</emoji> <b>Загрузка информации о сервере...</b>",
        "servinfo": (
            "<emoji document_id=5271897426117009417>🚘</emoji> <b>Информация о сервере</b>:\n\n"
            "<emoji document_id=5172854840321114816>💻</emoji> <b>Процессор:</b> {cpu_name} ({cpu_cores} ядер, {cpu_load}%)\n"
            "<emoji document_id=5174693704799093859>💻</emoji> <b>ОЗУ:</b> {ram_used} / {ram_total}MB ({ram_percent}%) DIMM\n"
            "<emoji document_id=5172854840321114816>💽</emoji> <b>Диск:</b> {disk_used} / {disk_total}GB ({disk_percent}%) {disk_type}\n"
            "<emoji document_id=5172622400986022463>🎮</emoji> <b>ГПУ:</b> NVIDIA GeForce RTX 4060 Ti\n"
            "🧠 <b>Видеопамять:</b> 1.4 / 8.0 ГБ (выделенная), 1.5 / 23.9 ГБ (общая)\n"
            "📅 <b>Драйвер:</b> 32.0.15.8088 (27.07.2025)\n"
            "🎮 <b>DirectX:</b> 12 (FL 12.1)\n\n"
            "<emoji document_id=5172474181664637769>💻</emoji> <b>Ядро:</b> {kernel}\n"
            "{arch_emoji} <b>Архитектура:</b> {arch}\n"
            "<emoji document_id=5172622400986022463>💻</emoji> <b>ОС:</b> {os}\n"
            "<emoji document_id=5172839378438849164>💻</emoji> <b>Python:</b> {python}"
        ),
        "_cls_doc": "Показывает информацию о сервере",
    }

    @loader.command(ru_doc="Показать информацию о сервере")
    async def serverinfo(self, message: Message):
        """Show server info"""
        message = await utils.answer(message, self.strings("loading"))

        inf = {
            "cpu_name": platform.processor() or "Unknown CPU",
            "cpu_cores": psutil.cpu_count(logical=True) or "n/a",
            "cpu_load": psutil.cpu_percent() or "n/a",
            "ram_used": bytes_to_megabytes(psutil.virtual_memory().used),
            "ram_total": bytes_to_megabytes(psutil.virtual_memory().total),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_used": bytes_to_gigabytes(shutil.disk_usage("/").used),
            "disk_total": bytes_to_gigabytes(shutil.disk_usage("/").total),
            "disk_percent": shutil.disk_usage("/").used * 100 // shutil.disk_usage("/").total,
            "disk_type": "NVMe SSD",
            "kernel": utils.escape_html(platform.release()),
            "arch": utils.escape_html(platform.architecture()[0]),
            "arch_emoji": "<emoji document_id=5172881503478088537>💻</emoji>" if "64" in platform.architecture()[0] else "<emoji document_id=5174703196676817427>💻</emoji>",
            "os": utils.escape_html(platform.system()),
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        }

        await utils.answer(message, self.strings("servinfo").format(**inf))


