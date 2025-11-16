# meta developer: @HookDevArch
# meta desc: Миграция Hook UserBot на новый сервер по SSH + SFTP

__version__ = (1, 4, 5)

# requires: paramiko

import asyncio
import os
import tarfile
import tempfile
import paramiko
import signal
import contextlib

from .. import loader, utils, main


STEPS = [
    "Упаковка Hook",
    "SSH подключение",
    "Передача архива",
    "Определение домашней директории",
    "Установка зависимостей",
    "Распаковка Hook",
    "Запуск Hook на новом сервере",
    "Отключение старого инстанса",
    "Готово",
]


def progress(step):
    done = "■" * step
    rest = "□" * (9 - step)
    percent = int(step / 9 * 100)
    return f"[{done}{rest}] {percent}% — {STEPS[step-1]}"


@loader.tds
class HookMigrateMod(loader.Module):
    """Миграция Hook UserBot на новый сервер по SSH"""

    strings = {"name": "HookMigrate"}

    # -------------------------
    # ПОИСК КАТАЛОГА HOOK
    # -------------------------
    def find_hook_dir(self):
        # Главный путь (реальный)
        possible_paths = [
            "/root/Hook",

            # fallback для установок в подпапке
            os.path.join(utils.get_base_dir(), "Hook"),
            os.path.join(os.path.dirname(utils.get_base_dir()), "Hook"),
        ]

        for path in possible_paths:
            if os.path.isdir(path):
                return path

        raise FileNotFoundError(
            "Каталог Hook не найден.\n"
            "Ожидался путь /root/Hook или рядом с местоположением UserBot."
        )

    # -------------------------
    # УПАКОВКА HOOK
    # -------------------------
    def pack_hook(self):
        hook_dir = self.find_hook_dir()

        tmp = tempfile.gettempdir()
        archive = os.path.join(tmp, "hook_migrate.tar.gz")

        with tarfile.open(archive, "w:gz") as tar:
            tar.add(hook_dir, arcname="Hook")

        return archive

    # -------------------------
    # SSH выполнение команд
    # -------------------------
    async def exec(self, ssh, cmd):
        stdin, stdout, stderr = ssh.exec_command(cmd)
        _ = stdout.read()
        err = stderr.read().decode().strip()
        return err

    # -------------------------
    # ГЛАВНАЯ КОМАНДА MIGRATE
    # -------------------------
    @loader.command()
    async def migrate(self, message):
        """
        .migrate USER@IP:PORT:PASSWORD
        """

        args = utils.get_args_raw(message)
        if not args or "@" not in args or ":" not in args:
            return await utils.answer(
                message,
                "<b>Использование:</b> .migrate user@host:22:password",
            )

        # Парсим
        user_host, port, password = args.split(":")
        user, host = user_host.split("@")
        port = int(port)

        msg = await utils.answer(message, "🚀 Начинаю миграцию...")

        async def step(n, extra=""):
            text = f"🔄 <b>Миграция Hook</b>\n\n{progress(n)}"
            if extra:
                text += "\n" + extra
            await utils.answer(msg, text)

        # ----------------------------
        # 1. УПАКОВКА
        # ----------------------------
        await step(1)
        try:
            archive = self.pack_hook()
        except Exception as e:
            return await utils.answer(msg, f"❌ Ошибка упаковки: {e}")

        # ----------------------------
        # 2. SSH
        # ----------------------------
        await step(2)
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host, port=port, username=user, password=password)
            sftp = ssh.open_sftp()
        except Exception as e:
            return await utils.answer(msg, f"❌ Ошибка SSH: {e}")

        # ----------------------------
        # 3. ПЕРЕДАЧА АРХИВА
        # ----------------------------
        await step(3)
        remote_archive = "/tmp/hook_migrate.tar.gz"

        try:
            sftp.put(archive, remote_archive)
            sftp.close()
        except Exception as e:
            return await utils.answer(msg, f"❌ Ошибка SFTP: {e}")

        # ----------------------------
        # 4. ДОМАШНЯЯ ДИРЕКТОРИЯ
        # ----------------------------
        await step(4)
        stdin, stdout, stderr = ssh.exec_command(f"eval echo ~{user}")
        home_dir = stdout.read().decode().strip()

        if not home_dir:
            home_dir = f"/Users/{user}"

        # Определяем ОС
        stdin, stdout, stderr = ssh.exec_command("uname")
        osname = stdout.read().decode().strip()
        is_mac = osname == "Darwin"

        # ----------------------------
        # 5–7. УСТАНОВКА И ЗАПУСК HOOK
        # ----------------------------
        await step(5)

        if is_mac:
            install = f"""
mkdir -p {home_dir}/Hook &&
tar -xzf /tmp/hook_migrate.tar.gz -C {home_dir} &&
cd {home_dir}/Hook &&
brew install python git || true &&
python3 -m venv .venv &&
source .venv/bin/activate &&
pip install -r requirements.txt &&
python3 -m hook --root
"""
        else:
            install = f"""
mkdir -p {home_dir}/Hook &&
tar -xzf /tmp/hook_migrate.tar.gz -C {home_dir} &&
cd {home_dir}/Hook &&
sudo apt update &&
sudo apt install -y git libcairo2 python3 python3-pip &&
pip3 install -r requirements.txt --break-system-packages &&
python3 -m hook --root
"""

        err = await self.exec(ssh, install)
        if err:
            await step(5, f"<b>Предупреждение:</b>\n<code>{err}</code>")

        # Проверяем запуск
        stdin, stdout, stderr = ssh.exec_command("pgrep -f 'python3 -m hook'")
        new_pid = stdout.read().decode().strip()

        if not new_pid:
            return await utils.answer(
                msg,
                "⚠️ <b>Hook НЕ запустился на новом сервере.</b>\n"
                "Отключение старого инстанса ОТМЕНЕНО."
            )

        ssh.close()

        # ----------------------------
        # 8. ОТКЛЮЧЕНИЕ СТАРОГО
        # ----------------------------
        await step(8)
        await utils.answer(
            msg,
            "✅ <b>Hook успешно запущен на новом сервере.</b>\n"
            "Старый инстанс будет отключён."
        )

        # ----------------------------
        # *Вариант A: мягкое завершение*
        # ----------------------------
        try:
            with contextlib.suppress(Exception):
                await main.hook.web.stop()

            for client in self.allclients:
                with contextlib.suppress(Exception):
                    await client.disconnect()

            os._exit(0)

        except Exception:
            pass

        # ----------------------------
        # *Вариант C: аварийное завершение*
        # ----------------------------
        try:
            os.kill(os.getpid(), signal.SIGKILL)
        except Exception:
            pass

        return
