# meta developer: @HookDevArch
# meta desc: Миграция Hook UserBot на новый сервер по SSH + SFTP

__version__ = (1, 3, 0)

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
    """Миграция Hook UserBot на другой сервер"""

    strings = {"name": "HookMigrate"}

    # Универсальный поиск каталога Hook
    def find_hook_dir(self):
        possible_paths = [
            "/root/Hook",  # истинный путь на твоём сервере
            os.path.join(utils.get_base_dir(), "Hook"),
            os.path.join(os.path.dirname(utils.get_base_dir()), "Hook"),
        ]

        for path in possible_paths:
            if os.path.isdir(path):
                return path

        raise FileNotFoundError(
            "Каталог Hook не найден. Убедитесь, что он находится в /root/Hook."
        )

    # Упаковка Hook в архив
    def pack_hook(self):
        hook_dir = self.find_hook_dir()
        tmp = tempfile.gettempdir()
        archive_path = os.path.join(tmp, "hook_migrate.tar.gz")

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(hook_dir, arcname="Hook")

        return archive_path

    # Исполнение команд по SSH
    async def exec(self, ssh, cmd):
        stdin, stdout, stderr = ssh.exec_command(cmd)
        _ = stdout.read()
        err = stderr.read().decode().strip()
        return err

    @loader.command()
    async def migrate(self, message):
        """
        .migrate USER@IP:PORT:PASSWORD
        """

        args = utils.get_args_raw(message)
        if not args or "@" not in args or ":" not in args:
            return await utils.answer(
                message,
                "<b>Использование:</b>\n"
                ".migrate user@host:22:password",
            )

        # Парсим команду
        user_host, port, password = args.split(":")
        user, host = user_host.split("@")
        port = int(port)

        msg = await utils.answer(message, "🚀 Начинаю миграцию...")

        async def step(s, extra=""):
            txt = f"🔄 <b>Миграция Hook</b>\n\n{progress(s)}"
            if extra:
                txt += "\n" + extra
            await utils.answer(msg, txt)

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
        # 4. ОПРЕДЕЛЕНИЕ ДОМАШНЕЙ ДИРЕКТОРИИ
        # ----------------------------
        await step(4)
        stdin, stdout, stderr = ssh.exec_command(f"eval echo ~{user}")
        home_dir = stdout.read().decode().strip()

        if not home_dir:
            home_dir = f"/Users/{user}"  # fallback для macOS

        # Определяем ОС
        stdin, stdout, stderr = ssh.exec_command("uname")
        osname = stdout.read().decode().strip()
        is_mac = osname == "Darwin"

        # ----------------------------
        # 5–7. УСТАНОВКА И ЗАПУСК НА НОВОМ СЕРВЕРЕ
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
            await utils.answer(msg, f"⚠️ Предупреждение:\n<code>{err}</code>")

        # Проверяем, что Hook запущен
        stdin, stdout, stderr = ssh.exec_command("pgrep -f 'python3 -m hook'")
        new_pid = stdout.read().decode().strip()

        if not new_pid:
            return await utils.answer(
                msg,
                "⚠️ <b>Hook НЕ запустился на новом сервере.</b>\n"
                "Отключение старого инстанса отменено."
            )

        ssh.close()

        # ----------------------------
        # 8. ОТКЛЮЧЕНИЕ СТАРОГО ИНСТАНСА
        # ----------------------------
        await step(8)
        await utils.answer(
            msg,
            "✅ <b>Hook успешно запущен на новом сервере.</b>\n"
            "Старый инстанс будет отключён."
        )

        # ----------------------------
        # ГРАЦИОЗНОЕ ЗАВЕРШЕНИЕ (вариант A)
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
        # FALLBACK (вариант C)
        # ----------------------------
        try:
            os.kill(os.getpid(), signal.SIGKILL)
        except Exception:
            pass

        return
    strings = {"name": "HookMigrate"}

    # Упаковка каталога Hook
    def pack_hook(self):
        base = utils.get_base_dir()
        hook_dir = os.path.join(base, "Hook")

        if not os.path.isdir(hook_dir):
            raise FileNotFoundError("Каталог Hook не найден.")

        tmp = tempfile.gettempdir()
        archive = os.path.join(tmp, "hook_migrate.tar.gz")

        with tarfile.open(archive, "w:gz") as tar:
            tar.add(hook_dir, arcname="Hook")

        return archive

    # Выполнение команды по SSH
    async def exec(self, ssh, cmd):
        stdin, stdout, stderr = ssh.exec_command(cmd)
        _ = stdout.read()
        err = stderr.read().decode().strip()
        return err

    @loader.command()
    async def migrate(self, message):
        """
        .migrate USER@IP:PORT:PASSWORD
        """

        args = utils.get_args_raw(message)
        if not args or "@" not in args or ":" not in args:
            return await utils.answer(
                message,
                "<b>Использование:</b>\n"
                ".migrate user@host:22:password",
            )

        # Парсинг строки
        user_host, port, password = args.split(":")
        user, host = user_host.split("@")
        port = int(port)

        msg = await utils.answer(message, "🚀 Начинаю миграцию...")

        async def step(s, extra=""):
            text = (
                f"🔄 <b>Миграция Hook</b>\n\n{progress(s)}"
                + ("\n" + extra if extra else "")
            )
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
            return await utils.answer(msg, f"❌ SSH ошибка: {e}")

        # ----------------------------
        # 3. ПЕРЕДАЧА АРХИВА
        # ----------------------------
        await step(3)
        remote_archive = "/tmp/hook_migrate.tar.gz"
        try:
            sftp.put(archive, remote_archive)
            sftp.close()
        except Exception as e:
            return await utils.answer(msg, f"❌ SFTP ошибка: {e}")

        # ----------------------------
        # 4. ОПРЕДЕЛЕНИЕ ДОМАШНЕЙ ДИРЕКТОРИИ
        # ----------------------------
        await step(4)
        stdin, stdout, stderr = ssh.exec_command(f"eval echo ~{user}")
        home_dir = stdout.read().decode().strip()

        if not home_dir:
            home_dir = f"/Users/{user}"  # fallback for macOS

        # Определяем ОС
        stdin, stdout, stderr = ssh.exec_command("uname")
        osname = stdout.read().decode().strip()
        is_mac = osname == "Darwin"

        # ----------------------------
        # 5–7. УСТАНОВКА И ЗАПУСК НА НОВОМ СЕРВЕРЕ
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
            await utils.answer(msg, f"⚠️ Предупреждение:\n<code>{err}</code>")

        # Проверка что новый Hook запустился
        stdin, stdout, stderr = ssh.exec_command("pgrep -f 'python3 -m hook'")
        new_pid = stdout.read().decode().strip()

        if not new_pid:
            return await utils.answer(
                msg,
                "⚠️ <b>Hook НЕ запустился на новом сервере.</b>\n"
                "Отключение старого инстанса отменено."
            )

        ssh.close()

        # ----------------------------
        # 8. ОТКЛЮЧЕНИЕ СТАРОЙ МАШИНЫ
        # ----------------------------
        await step(8)
        await utils.answer(
            msg,
            (
                "✅ <b>Hook успешно запущен на новом сервере.</b>\n"
                "Старый инстанс будет отключён."
            )
        )

        # ----------------------------
        # КОРРЕКТНОЕ ЗАВЕРШЕНИЕ (ВАРИАНТ A)
        # ----------------------------
        try:
            with contextlib.suppress(Exception):
                await main.hook.web.stop()

            # отключаем всех клиентов
            for client in self.allclients:
                with contextlib.suppress(Exception):
                    await client.disconnect()

            # аварийное завершение процесса
            os._exit(0)

        except Exception:
            pass

        # ----------------------------
        # FALLBACK (ВАРИАНТ C)
        # ----------------------------
        try:
            os.kill(os.getpid(), signal.SIGKILL)
        except Exception:
            pass

        # Чтобы линтер не жаловался
        return
