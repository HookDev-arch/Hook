"""Main bot page"""

import asyncio
import collections
import functools
import logging
import os
import re
import string
import time
import sys
from pathlib import Path

import aiohttp_jinja2
import requests
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiohttp import web
from hikkatl.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
    YouBlockedUserError,
)
from hikkatl.password import compute_check
from hikkatl.sessions import MemorySession
from hikkatl.tl.functions.account import GetPasswordRequest
from hikkatl.tl.functions.auth import CheckPasswordRequest
from hikkatl.tl.functions.contacts import UnblockRequest
from hikkatl.utils import parse_phone

from .. import database, main, utils
from .._internal import restart
from ..tl_cache import CustomTelegramClient
from ..version import __version__

DATA_DIR = (
    "/data"
    if "DOCKER" in os.environ
    else os.path.normpath(os.path.join(utils.get_base_dir(), ".."))
)

logger = logging.getLogger(__name__)

class Web:
    def __init__(self, **kwargs):
        self.sign_in_clients = {}
        self._pending_client = None
        self._qr_login = None
        self._qr_task = None
        self._2fa_needed = None
        self._sessions = []
        self._ratelimit = {}
        self.api_token = kwargs.pop("api_token")
        self.data_root = kwargs.pop("data_root")
        self.connection = kwargs.pop("connection")
        self.proxy = kwargs.pop("proxy")
        self.loader = kwargs.pop("loader")  # Добавляем loader для управления модулями

        # Добавляем новые маршруты
        self.app.router.add_get("/", self.root)
        self.app.router.add_put("/set_api", self.set_tg_api)
        self.app.router.add_post("/send_tg_code", self.send_tg_code)
        self.app.router.add_post("/check_session", self.check_session)
        self.app.router.add_post("/web_auth", self.web_auth)
        self.app.router.add_post("/tg_code", self.tg_code)
        self.app.router.add_post("/finish_login", self.finish_login)
        self.app.router.add_post("/custom_bot", self.custom_bot)
        self.app.router.add_post("/init_qr_login", self.init_qr_login)
        self.app.router.add_post("/get_qr_url", self.get_qr_url)
        self.app.router.add_post("/qr_2fa", self.qr_2fa)
        self.app.router.add_post("/can_add", self.can_add)
        self.app.router.add_get("/modules", self.modules_page)  # Страница управления модулями
        self.app.router.add_post("/upload_module", self.upload_module)  # Загрузка модуля
        self.app.router.add_post("/delete_module", self.delete_module)  # Удаление модуля
        self.app.router.add_post("/restart", self.restart)  # Перезапуск юзербота

        self.api_set = asyncio.Event()
        self.clients_set = asyncio.Event()

    @property
    def _platform_emoji(self) -> str:
        return {
            "vds": "https://github.com/hikariatama/assets/raw/master/waning-crescent-moon_1f318.png",
            "lavhost": "https://github.com/hikariatama/assets/raw/master/victory-hand_270c-fe0f.png",
            "termux": "https://github.com/hikariatama/assets/raw/master/smiling-face-with-sunglasses_1f60e.png",
            "docker": "https://github.com/hikariatama/assets/raw/master/spouting-whale_1f433.png",
        }[
            (
                "lavhost"
                if "LAVHOST" in os.environ
                else (
                    "termux"
                    if "com.termux" in os.environ.get("PREFIX", "")
                    else "docker"
                    if "DOCKER" in os.environ
                    else "vds"
                )
            )
        ]

    @aiohttp_jinja2.template("root.jinja2")
    async def root(self, _):
        return {
            "skip_creds": self.api_token is not None,
            "tg_done": bool(self.client_data),
            "lavhost": "LAVHOST" in os.environ,
            "platform_emoji": self._platform_emoji,
        }

    async def check_session(self, request: web.Request) -> web.Response:
        return web.Response(body=("1" if self._check_session(request) else "0"))

    def wait_for_api_token_setup(self):
        return self.api_set.wait()

    def wait_for_clients_setup(self):
        return self.clients_set.wait()

    def _check_session(self, request: web.Request) -> bool:
        return (
            request.cookies.get("session", None) in self._sessions
            if main.hook.clients
            else True
        )

    async def _check_bot(
        self,
        client: CustomTelegramClient,
        username: str,
    ) -> bool:
        async with client.conversation("@BotFather", exclusive=False) as conv:
            try:
                m = await conv.send_message("/token")
            except YouBlockedUserError:
                await client(UnblockRequest(id="@BotFather"))
                m = await conv.send_message("/token")

            r = await conv.get_response()

            await m.delete()
            await r.delete()

            if not hasattr(r, "reply_markup") or not hasattr(r.reply_markup, "rows"):
                return False

            for row in r.reply_markup.rows:
                for button in row.buttons:
                    if username != button.text.strip("@"):
                        continue

                    m = await conv.send_message("/cancel")
                    r = await conv.get_response()

                    await m.delete()
                    await r.delete()

                    return True

    async def custom_bot(self, request: web.Request) -> web.Response:
        if not self._check_session(request):
            return web.Response(status=401)

        text = await request.text()
        client = self._pending_client
        db = database.Database(client)
        await db.init()

        text = text.strip("@")

        if any(
            litera not in (string.ascii_letters + string.digits + "_")
            for litera in text
        ) or not text.lower().endswith("bot"):
            return web.Response(body="OCCUPIED")

        try:
            await client.get_entity(f"@{text}")
        except ValueError:
            pass
        else:
            if not await self._check_bot(client, text):
                return web.Response(body="OCCUPIED")

        db.set("hikka.inline", "custom_bot", text)
        return web.Response(body="OK")

    async def set_tg_api(self, request: web.Request) -> web.Response:
        if not self._check_session(request):
            return web.Response(status=401, body="Authorization required")

        text = await request.text()

        if len(text) < 36:
            return web.Response(
                status=400,
                body="API ID and HASH pair has invalid length",
            )

        api_id = text[32:]
        api_hash = text[:32]

        if any(c not in string.hexdigits for c in api_hash) or any(
            c not in string.digits for c in api_id
        ):
            return web.Response(
                status=400,
                body="You specified invalid API ID and/or API HASH",
            )

        main.save_config_key("api_id", int(api_id))
        main.save_config_key("api_hash", api_hash)

        self.api_token = collections.namedtuple("api_token", ("ID", "HASH"))(
            api_id,
            api_hash,
        )

        self.api_set.set()
        return web.Response(body="ok")

    async def _qr_login_poll(self):
        logged_in = False
        self._2fa_needed = False
        logger.debug("Waiting for QR login to complete")
        while not logged_in:
            try:
                logged_in = await self._qr_login.wait(10)
            except asyncio.TimeoutError:
                logger.debug("Recreating QR login")
                try:
                    await self._qr_login.recreate()
                except SessionPasswordNeededError:
                    self._2fa_needed = True
                    return
            except SessionPasswordNeededError:
                self._2fa_needed = True
                break

        logger.debug("QR login completed. 2FA needed: %s", self._2fa_needed)
        self._qr_login = True

    async def init_qr_login(self, request: web.Request) -> web.Response:
        if self.client_data and "LAVHOST" in os.environ:
            return web.Response(status=403, body="Forbidden by host EULA")

        if not self._check_session(request):
            return web.Response(status=401)

        if self._pending_client is not None:
            self._pending_client = None
            self._qr_login = None
            if self._qr_task:
                self._qr_task.cancel()
                self._qr_task = None

            self._2fa_needed = False
            logger.debug("QR login cancelled, new session created")

        client = self._get_client()
        self._pending_client = client

        await client.connect()
        self._qr_login = await client.qr_login()
        self._qr_task = asyncio.ensure_future(self._qr_login_poll())

        return web.Response(body=self._qr_login.url)

    async def get_qr_url(self, request: web.Request) -> web.Response:
        if not self._check_session(request):
            return web.Response(status=401)

        if self._qr_login is True:
            if self._2fa_needed:
                return web.Response(status=403, body="2FA")

            await main.hook.save_client_session(self._pending_client)
            return web.Response(status=200, body="SUCCESS")

        if self._qr_login is None:
            await self.init_qr_login(request)

        if self._qr_login is None:
            return web.Response(
                status=500,
                body="Internal Server Error: Unable to initialize QR login",
            )

        return web.Response(status=201, body=self._qr_login.url)

    def _get_client(self) -> CustomTelegramClient:
        return CustomTelegramClient(
            MemorySession(),
            self.api_token.ID,
            self.api_token.HASH,
            connection=self.connection,
            proxy=self.proxy,
            connection_retries=None,
            device_model=main.get_app_name(),
            system_version="Windows 10",
            app_version=".".join(map(str, __version__)) + " x64",
            lang_code="en",
            system_lang_code="en-US",
        )

    async def can_add(self, request: web.Request) -> web.Response:
        if self.client_data and "LAVHOST" in os.environ:
            return web.Response(status=403, body="Forbidden by host EULA")

        return web.Response(status=200, body="Yes")

    async def send_tg_code(self, request: web.Request) -> web.Response:
        if not self._check_session(request):
            return web.Response(status=401, body="Authorization required")

        if self.client_data and "LAVHOST" in os.environ:
            return web.Response(status=403, body="Forbidden by host EULA")

        if self._pending_client:
            return web.Response(status=208, body="Already pending")

        text = await request.text()
        phone = parse_phone(text)

        if not phone:
            return web.Response(status=400, body="Invalid phone number")

        client = self._get_client()

        self._pending_client = client

        await client.connect()
        try:
            await client.send_code_request(phone)
        except FloodWaitError as e:
            return web.Response(status=429, body=self._render_fw_error(e))

        return web.Response(body="ok")

    @staticmethod
    def _render_fw_error(e: FloodWaitError) -> str:
        seconds, minutes, hours = (
            e.seconds % 3600 % 60,
            e.seconds % 3600 // 60,
            e.seconds // 3600,
        )
        seconds, minutes, hours = (
            f"{seconds} second(-s)",
            f"{minutes} minute(-s) " if minutes else "",
            f"{hours} hour(-s) " if hours else "",
        )
        return (
            f"You got FloodWait for {hours}{minutes}{seconds}. Wait the specified"
            " amount of time and try again."
        )

    async def qr_2fa(self, request: web.Request) -> web.Response:
        if not self._check_session(request):
            return web.Response(status=401)

        text = await request.text()

        logger.debug("2FA code received for QR login: %s", text)

        try:
            await self._pending_client._on_login(
                (
                    await self._pending_client(
                        CheckPasswordRequest(
                            compute_check(
                                await self._pending_client(GetPasswordRequest()),
                                text.strip(),
                            )
                        )
                    )
                ).user
            )
        except PasswordHashInvalidError:
            logger.debug("Invalid 2FA code")
            return web.Response(
                status=403,
                body="Invalid 2FA password",
            )
        except FloodWaitError as e:
            logger.debug("FloodWait for 2FA code")
            return web.Response(
                status=421,
                body=(self._render_fw_error(e)),
            )

        logger.debug("2FA code accepted, logging in")
        await main.hook.save_client_session(self._pending_client)
        return web.Response()

    async def tg_code(self, request: web.Request) -> web.Response:
        if not self._check_session(request):
            return web.Response(status=401)

        text = await request.text()

        if len(text) < 6:
            return web.Response(status=400)

        split = text.split("\n", 2)

        if len(split) not in (2, 3):
            return web.Response(status=400)

        code = split[0]
        phone = parse_phone(split[1])
        password = split[2]

        if (
            (len(code) != 5 and not password)
            or any(c not in string.digits for c in code)
            or not phone
        ):
            return web.Response(status=400)

        if not password:
            try:
                await self._pending_client.sign_in(phone, code=code)
            except SessionPasswordNeededError:
                return web.Response(
                    status=401,
                    body="2FA Password required",
                )
            except PhoneCodeExpiredError:
                return web.Response(status=404, body="Code expired")
            except PhoneCodeInvalidError:
                return web.Response(status=403, body="Invalid code")
            except FloodWaitError as e:
                return web.Response(
                    status=421,
                    body=(self._render_fw_error(e)),
                )
        else:
            try:
                await self._pending_client.sign_in(phone, password=password)
            except PasswordHashInvalidError:
                return web.Response(
                    status=403,
                    body="Invalid 2FA password",
                )
            except FloodWaitError as e:
                return web.Response(
                    status=421,
                    body=(self._render_fw_error(e)),
                )

        await main.hook.save_client_session(self._pending_client)
        return web.Response()

    async def finish_login(self, request: web.Request) -> web.Response:
        if not self._check_session(request):
            return web.Response(status=401)

        if not self._pending_client:
            return web.Response(status=400)

        first_session = not bool(main.hook.clients)

        # Client is ready to pass in to dispatcher
        main.hook.clients = list(set(main.hook.clients + [self._pending_client]))
        self._pending_client = None

        self.clients_set.set()

        if not first_session:
            restart()

        return web.Response()

    async def web_auth(self, request: web.Request) -> web.Response:
        if self._check_session(request):
            return web.Response(body=request.cookies.get("session", "unauthorized"))

        token = utils.rand(8)

        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                "🔓 Authorize user",
                callback_data=f"authorize_web_{token}",
            )
        )

        ips = request.headers.get("X-FORWARDED-FOR", None) or request.remote
        cities = []

        for ip in re.findall(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", ips):
            if ip not in self._ratelimit:
                self._ratelimit[ip] = []

            if (
                len(
                    list(
                        filter(lambda x: time.time() - x < 3 * 60, self._ratelimit[ip])
                    )
                )
                >= 3
            ):
                return web.Response(status=429)

            self._ratelimit[ip] = list(
                filter(lambda x: time.time() - x < 3 * 60, self._ratelimit[ip])
            )

            self._ratelimit[ip] += [time.time()]
            try:
                res = (
                    await utils.run_sync(
                        requests.get,
                        f"https://freegeoip.app/json/{ip}",
                    )
                ).json()
                cities += [
                    f"<i>{utils.get_lang_flag(res['country_code'])} {res['country_name']} {res['region_name']} {res['city']} {res['zip_code']}</i>"
                ]
            except Exception:
                pass

        cities = (
            ("<b>🏢 Possible cities:</b>\n\n" + "\n".join(cities) + "\n")
            if cities
            else ""
        )

        ops = []

        for user in self.client_data.values():
            try:
                bot = user[0].inline.bot
                msg = await bot.send_message(
                    user[1].tg_id,
                    (
                        "🌘🔐 <b>Click button below to confirm web application"
                        f" ops</b>\n\n<b>Client IP</b>: {ips}\n{cities}\n<i>If you did"
                        " not request any codes, simply ignore this message</i>\n\n⚠️"
                        " <b>Warning!</b> If you did not make any actions in the web"
                        " interface, <b>do not click the button below</b>, as it might"
                        " give the user on the other end the access to your account!"
                    ),
                    disable_web_page_preview=True,
                    reply_markup=markup,
                )
                ops += [
                    functools.partial(
                        bot.delete_message,
                        chat_id=msg.chat.id,
                        message_id=msg.message_id,
                    )
                ]
            except Exception:
                pass

        session = f"hook_{utils.rand(16)}"

        if not ops:
            # If no auth message was sent, just leave it empty
            # probably, request was a bug and user doesn't have
            # inline bot or did not authorize any sessions
            return web.Response(body=session)

        if not await main.hook.wait_for_web_auth(token):
            for op in ops:
                await op()
            return web.Response(body="TIMEOUT")

        for op in ops:
            await op()

        self._sessions += [session]

        return web.Response(body=session)

    # Новые методы для управления модулями и перезапуском

    async def modules_page(self, request: web.Request) -> web.Response:
        """Отображает страницу управления модулями"""
        if not self._check_session(request):
            return web.Response(text="Unauthorized", status=401)

        # Получаем список модулей из loader
        modules = self.loader.modules
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Hook - Управление модулями</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background: linear-gradient(135deg, #1e3a8a, #3b82f6);
                    color: #fff;
                    padding: 20px;
                    margin: 0;
                }
                h1 {
                    text-align: center;
                    margin-bottom: 20px;
                }
                table {
                    width: 100%;
                    max-width: 800px;
                    margin: 0 auto;
                    border-collapse: collapse;
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 10px;
                    overflow: hidden;
                }
                th, td {
                    padding: 15px;
                    text-align: left;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.2);
                }
                th {
                    background: rgba(255, 255, 255, 0.2);
                }
                button {
                    padding: 8px 15px;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                    transition: background 0.3s ease;
                }
                .delete-btn {
                    background: #ef4444;
                    color: #fff;
                }
                .delete-btn:hover {
                    background: #dc2626;
                }
                .restart-btn {
                    background: #10b981;
                    color: #fff;
                    margin: 20px auto;
                    display: block;
                }
                .restart-btn:hover {
                    background: #059669;
                }
                .upload-form {
                    text-align: center;
                    margin: 20px 0;
                }
                input[type="file"] {
                    padding: 10px;
                    background: rgba(255, 255, 255, 0.2);
                    border-radius: 5px;
                    color: #fff;
                }
                input[type="submit"] {
                    padding: 10px 20px;
                    background: #3b82f6;
                    color: #fff;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                }
                input[type="submit"]:hover {
                    background: #1e3a8a;
                }
            </style>
        </head>
        <body>
            <h1>Управление модулями Hook 🚀</h1>

            <div class="upload-form">
                <form action="/upload_module" method="post" enctype="multipart/form-data">
                    <input type="file" name="module_file" accept=".py" required>
                    <input type="submit" value="Загрузить модуль">
                </form>
            </div>

            <table>
                <tr>
                    <th>Модуль</th>
                    <th>Действия</th>
                </tr>
        """

        # Добавляем строки для каждого модуля
        for mod in modules:
            mod_name = mod.strings.get("name", "Unknown")
            html += f"""
                <tr>
                    <td>{mod_name}</td>
                    <td>
                        <form action="/delete_module" method="post" style="display:inline;">
                            <input type="hidden" name="module_name" value="{mod_name}">
                            <button type="submit" class="delete-btn">Удалить</button>
                        </form>
                    </td>
                </tr>
            """

        html += """
            </table>

            <form action="/restart" method="post">
                <button type="submit" class="restart-btn">Перезапустить юзербота</button>
            </form>
        </body>
        </html>
        """
        return web.Response(text=html, content_type="text/html")

    async def upload_module(self, request: web.Request) -> web.Response:
        """Обрабатывает загрузку нового модуля"""
        if not self._check_session(request):
            return web.Response(text="Unauthorized", status=401)

        reader = await request.multipart()
        field = await reader.next()
        if not field or field.name != "module_file":
            return web.Response(text="No file uploaded", status=400)

        # Сохраняем файл в папку modules
        filename = field.filename
        if not filename.endswith(".py"):
            return web.Response(text="Only .py files are allowed", status=400)

        module_path = Path("hook") / "modules" / filename
        with open(module_path, "wb") as f:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                f.write(chunk)

        # Перезагружаем модули
        try:
            await self.loader.load_module(str(module_path))
            return web.Response(
                text=f"Module {filename} uploaded and loaded successfully! <a href='/modules'>Back to Modules</a>",
                content_type="text/html"
            )
        except Exception as e:
            return web.Response(
                text=f"Failed to load module {filename}: {str(e)} <a href='/modules'>Back to Modules</a>",
                status=500,
                content_type="text/html"
            )

    async def delete_module(self, request: web.Request) -> web.Response:
        """Обрабатывает удаление модуля"""
        if not self._check_session(request):
            return web.Response(text="Unauthorized", status=401)

        data = await request.post()
        module_name = data.get("module_name")
        if not module_name:
            return web.Response(text="Module name not provided", status=400)

        # Удаляем модуль
        try:
            await self.loader.unload_module(module_name)
            module_file = Path("hook") / "modules" / f"{module_name.lower()}.py"
            if module_file.exists():
                module_file.unlink()
            return web.Response(
                text=f"Module {module_name} deleted successfully! <a href='/modules'>Back to Modules</a>",
                content_type="text/html"
            )
        except Exception as e:
            return web.Response(
                text=f"Failed to delete module {module_name}: {str(e)} <a href='/modules'>Back to Modules</a>",
                status=500,
                content_type="text/html"
            )

    async def restart(self, request: web.Request) -> web.Response:
        """Обрабатывает перезапуск юзербота"""
        if not self._check_session(request):
            return web.Response(text="Unauthorized", status=401)

        # Перезапускаем юзербота
        logging.info("Restarting Hook via web interface...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
        return web.Response(
            text="Restart initiated! Please wait a few seconds and refresh the page.",
            content_type="text/html"
        )