# meta developer: @HookDevArch
# meta desc: Миграция Hook UserBot на новый сервер по SSH + SFTP

__version__ = (1, 5, 0)

# requires: paramiko

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


def progress(step: int) -> str:
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
    def find_hook_dir(self) -> str:
        possible_paths = [
            "/root/Hook",  # твой реальный путь
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
    # УПАКОВКА HOOK (БЕЗ .venv!)
    # -------------------------
    def pack_hook(self) -> str:
        hook_dir = self.find_hook_dir()

        tmp = tempfile.gettempdir()
        archive = os.path.join(tmp, "hook_migrate.tar.gz")

        # Пакуем только код, без виртуалок и кешей
        with tarfile.open(archive, "w:gz") as tar:
            for root, dirs, files in os.walk(hook_dir):
                # Не тянем .venv
                if ".venv" in dirs:
                    dirs.remove(".venv")

                # Не тянем __pycache__
                if "__pycache__" in dirs:
                    dirs.remove("__pycache__")

                rel_root = os.path.relpath(root, hook_dir)
                for name in files:
                    full_path = os.path.join(root, name)
                    if rel_root == ".":
                        arcname = os.path.join("Hook", name)
                    else:
                        arcname = os.path.join("Hook", rel_root, name)

                    tar.add(full_path, arcname=arcname)

        return archive

    # -------------------------
    # ВЫПОЛНЕНИЕ КОМАНД ПО SSH
    # -------------------------
    async def exec(self, ssh: paramiko.SSHClient, cmd: str) -> str:
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
                "<b>Использование:</b> <code>.migrate user@host:22:password</code>",
            )

        user_host, port, password = args.split(":")
        user, host = user_host.split("@")
        port = int(port)

        msg = await utils.answer(message, "🚀 Начинаю миграцию...")

        async def step(n: int, extra: str = ""):
            text = f"🔄 <b>Миграция Hook</b>\n\n{progress(n)}"
            if extra:
                text += "\n" + extra
            await utils.answer(msg, text)

        # ----------------------------
        # 1. УПАКОВКА HOOK
        # ----------------------------
        await step(1)
        try:
            archive = self.pack_hook()
        except Exception as e:
            return await utils.answer(
                msg,
                f"❌ <b>Ошибка упаковки Hook:</b>\n<code>{utils.escape_html(str(e))}</code>",
            )

        # ----------------------------
        # 2. SSH ПОДКЛЮЧЕНИЕ
        # ----------------------------
        await step(2)
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host, port=port, username=user, password=password)
            sftp = ssh.open_sftp()
        except Exception as e:
            return await utils.answer(
                msg,
                f"❌ <b>Ошибка SSH-подключения:</b>\n<code>{utils.escape_html(str(e))}</code>",
            )

        # ----------------------------
        # 3. ПЕРЕДАЧА АРХИВА
        # ----------------------------
        await step(3)
        remote_archive = "/tmp/hook_migrate.tar.gz"

        try:
            sftp.put(archive, remote_archive)
            sftp.close()
        except Exception as e:
            return await utils.answer(
                msg,
                f"❌ <b>Ошибка передачи архива:</b>\n<code>{utils.escape_html(str(e))}</code>",
            )

        # ----------------------------
        # 4. ДОМАШНЯЯ ДИРЕКТОРИЯ
        # ----------------------------
        await step(4)
        stdin, stdout, stderr = ssh.exec_command(f"eval echo ~{user}")
        home_dir = stdout.read().decode().strip()

        if not home_dir:
            home_dir = f"/Users/{user}"  # fallback для macOS

        # Определение ОС
        stdin, stdout, stderr = ssh.exec_command("uname")
        osname = stdout.read().decode().strip()
        is_mac = osname == "Darwin"

        # ----------------------------
        # 5–7. УСТАНОВКА И ЗАПУСК
        # ----------------------------
        await step(5)

        # Лог файл на новом сервере
        install_log = "/tmp/hook_migrate_install.log"

        if is_mac:
            install = f"""
set -e
LOG="{install_log}"
echo "=== Hook migrate begin (macOS) ===" > "$LOG"
mkdir -p "{home_dir}/Hook" >>"$LOG" 2>&1
tar -xzf "{remote_archive}" -C "{home_dir}" >>"$LOG" 2>&1
cd "{home_dir}/Hook" >>"$LOG" 2>&1
brew install python git >>"$LOG" 2>&1 || true
python3 -m venv .venv >>"$LOG" 2>&1
source .venv/bin/activate >>"$LOG" 2>&1
pip install --upgrade pip wheel setuptools >>"$LOG" 2>&1
pip install -r requirements.txt >>"$LOG" 2>&1
python3 -m hook --root >>"$LOG" 2>&1
"""
        else:
            install = f"""
set -e
LOG="{install_log}"
echo "=== Hook migrate begin (Linux) ===" > "$LOG"
mkdir -p "{home_dir}/Hook" >>"$LOG" 2>&1
tar -xzf "{remote_archive}" -C "{home_dir}" >>"$LOG" 2>&1
cd "{home_dir}/Hook" >>"$LOG" 2>&1
sudo apt update >>"$LOG" 2>&1
sudo apt install -y git libcairo2 python3 python3-pip >>"$LOG" 2>&1
python3 -m venv .venv >>"$LOG" 2>&1
source .venv/bin/activate >>"$LOG" 2>&1
pip install --upgrade pip wheel setuptools >>"$LOG" 2>&1
pip install -r requirements.txt >>"$LOG" 2>&1
python3 -m hook --root >>"$LOG" 2>&1
"""

        # Выполняем установку под sh -lc
        err = await self.exec(ssh, f"/bin/sh -lc '{install}'")
        if err:
            await step(
                5,
                f"⚠️ <b>Предупреждение при установке:</b>\n<code>{utils.escape_html(err)}</code>\n"
                f"<i>Подробный лог на новом сервере:</i> <code>{install_log}</code>",
            )

        # Проверяем, что Hook реально запустился
        stdin, stdout, stderr = ssh.exec_command("pgrep -f 'python3 -m hook'")
        new_pid = stdout.read().decode().strip()

        if not new_pid:
            ssh.close()
            return await utils.answer(
                msg,
                "⚠️ <b>Hook НЕ запустился на новом сервере.</b>\n"
                f"Проверь лог на новом сервере: <code>{install_log}</code>\n"
                "Старый инстанс НЕ будет отключён.",
            )

        ssh.close()

        # ----------------------------
        # 8. ОТКЛЮЧЕНИЕ СТАРОГО
        # ----------------------------
        await step(8)
        await utils.answer(
            msg,
            "✅ <b>Hook успешно запущен на новом сервере.</b>\n"
            "Старый инстанс будет отключён.",
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
