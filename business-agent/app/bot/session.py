"""HTTP-сессия Telegram, которая учитывает окружение: HTTPS_PROXY и SSL_CERT_FILE.

Стандартная сессия aiogram берёт сертификаты только из certifi и игнорирует прокси из
переменных окружения — за корпоративным прокси с собственным CA она не подключится.
"""
import os
import ssl

from aiohttp import ClientSession
from aiogram.__meta__ import __version__
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp.hdrs import USER_AGENT
from aiohttp.http import SERVER_SOFTWARE


class EnvAwareSession(AiohttpSession):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        cafile = os.environ.get("SSL_CERT_FILE")
        if cafile and os.path.exists(cafile):
            self._connector_init["ssl"] = ssl.create_default_context(cafile=cafile)

    async def create_session(self) -> ClientSession:
        if self._should_reset_connector:
            await self.close()
        if self._session is None or self._session.closed:
            self._session = ClientSession(
                connector=self._connector_type(**self._connector_init),
                headers={USER_AGENT: f"{SERVER_SOFTWARE} aiogram/{__version__}"},
                trust_env=True,
            )
            self._should_reset_connector = False
        return self._session
