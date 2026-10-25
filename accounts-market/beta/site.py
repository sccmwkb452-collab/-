"""Beta preview site: a web chat that drives the real bot logic.

* Runs inside the bot process, on the same HTTP server as /healthz.
* Disabled unless BETA_SITE=true; refuses to start with ENVIRONMENT=production.
* Reachable only at /beta/<BETA_KEY>/ and not linked from the bot anywhere.
* Uses its own in-process Bot API imitation: no message ever reaches Telegram.
"""

from __future__ import annotations

import hmac
import itertools
import logging
import secrets
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, Message, MessageEntity, Update, User
from aiohttp import web

from beta.telegram import BetaTelegram

log = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parent / "static"
COOKIE = "beta_sid"
# Visitor ids live far above real Telegram ids, so they never clash with real users.
USER_ID_BASE = 7_000_000_000_000
ADMIN_ID = USER_ID_BASE  # one shared admin identity for the "admin mode" switch


@dataclass
class Visitor:
    user_id: int
    admin: bool = False

    @property
    def chat_id(self) -> int:
        return ADMIN_ID if self.admin else self.user_id


class BetaSite:
    def __init__(self, dp: Dispatcher, token: str, key: str) -> None:
        self.dp = dp
        self.key = key
        self.tg = BetaTelegram()
        self.bot = Bot(token, session=self.tg, default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True))
        self.visitors: dict[str, Visitor] = {}
        self._updates = itertools.count(1)

    def owns(self, user_id: int) -> bool:
        return user_id >= USER_ID_BASE

    # ── updates ──────────────────────────────────────────────────────────────

    def _tg_user(self, v: Visitor) -> User:
        if v.admin:
            return User(id=ADMIN_ID, is_bot=False, first_name="Beta Admin", username="beta_admin")
        return User(id=v.user_id, is_bot=False, first_name="Beta", username=f"beta{v.user_id - USER_ID_BASE}")

    async def send_text(self, v: Visitor, text: str) -> None:
        text = text.strip()[:2000]
        if not text:
            return
        entities = None
        if text.startswith("/"):
            entities = [MessageEntity(type="bot_command", offset=0, length=len(text.split()[0]))]
        msg = self.tg.message(v.chat_id, sender=self._tg_user(v), text=text, entities=entities)
        self.tg.put(msg)
        await self.dp.feed_update(self.bot, Update(update_id=next(self._updates), message=msg))

    async def press(self, v: Visitor, message_id: int, data: str) -> None:
        message = self.tg.find(v.chat_id, message_id)
        if message is None:
            return
        cq = CallbackQuery(
            id=f"{v.chat_id}:{next(self._updates)}",
            from_user=self._tg_user(v),
            chat_instance="beta",
            data=data[:64],
            message=message,
        )
        await self.dp.feed_update(self.bot, Update(update_id=next(self._updates), callback_query=cq))

    # ── HTTP ─────────────────────────────────────────────────────────────────

    def _check(self, request: web.Request) -> None:
        if not hmac.compare_digest(request.match_info.get("key", ""), self.key):
            raise web.HTTPNotFound()

    def _visitor(self, request: web.Request) -> tuple[str, Visitor]:
        sid = request.cookies.get(COOKIE, "")
        if sid not in self.visitors:
            sid = secrets.token_urlsafe(16)
            self.visitors[sid] = Visitor(USER_ID_BASE + 1 + secrets.randbelow(10**9))
        return sid, self.visitors[sid]

    def _serialize(self, m: Message) -> dict:
        buttons = []
        if m.reply_markup:
            for row in m.reply_markup.inline_keyboard:
                buttons.append(
                    [
                        {
                            "text": b.text,
                            "data": b.callback_data,
                            "url": b.url,
                            "copy": b.copy_text.text if b.copy_text else None,
                            "style": b.style,
                        }
                        for b in row
                    ]
                )
        photo = None
        if m.photo:
            fid = m.photo[-1].file_id
            photo = f"media/{fid}" if fid in self.tg.media else "missing"
        mine = m.from_user is not None and not m.from_user.is_bot
        # Bot texts are stored exactly as sent, i.e. already in Telegram HTML.
        html = m.text if mine else (m.caption or m.text or "")
        return {"id": m.message_id, "mine": mine, "html": html or "", "photo": photo, "buttons": buttons}

    def _state(self, v: Visitor) -> dict:
        toasts = self.tg.toasts.pop(v.chat_id, [])
        return {
            "admin": v.admin,
            "messages": [self._serialize(m) for m in self.tg.chats.get(v.chat_id, [])],
            "toasts": [{"text": t, "alert": a} for t, a in toasts],
        }

    async def _respond(self, sid: str, v: Visitor) -> web.Response:
        response = web.json_response(self._state(v))
        response.set_cookie(COOKIE, sid, httponly=True, samesite="Strict", max_age=7 * 86400)
        return response

    async def page(self, request: web.Request) -> web.StreamResponse:
        self._check(request)
        if not request.path.endswith("/"):
            raise web.HTTPFound(request.path + "/")
        return web.FileResponse(STATIC / "index.html", headers={"X-Robots-Tag": "noindex", "Cache-Control": "no-store"})

    async def state(self, request: web.Request) -> web.Response:
        self._check(request)
        sid, v = self._visitor(request)
        if not self.tg.chats.get(v.chat_id):
            await self.send_text(v, "/start")
        return await self._respond(sid, v)

    async def action(self, request: web.Request) -> web.Response:
        self._check(request)
        sid, v = self._visitor(request)
        body = await request.json()
        kind = body.get("type")
        if kind == "text":
            await self.send_text(v, str(body.get("text", "")))
        elif kind == "press":
            await self.press(v, int(body.get("id", 0)), str(body.get("data", "")))
        elif kind == "admin":
            v.admin = bool(body.get("on"))
            if not self.tg.chats.get(v.chat_id):
                await self.send_text(v, "/start")
            if v.admin:
                await self.send_text(v, "/admin")
        elif kind == "reset":
            self.tg.chats.pop(v.chat_id, None)
            self.visitors.pop(sid, None)
            sid, v = self._visitor(request)
            await self.send_text(v, "/start")
        return await self._respond(sid, v)

    async def media(self, request: web.Request) -> web.Response:
        self._check(request)
        data = self.tg.media.get(request.match_info["fid"])
        if data is None:
            raise web.HTTPNotFound()
        return web.Response(body=data, content_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})

    def routes(self, app: web.Application) -> None:
        app.router.add_get("/beta/{key}", self.page)
        app.router.add_get("/beta/{key}/", self.page)
        app.router.add_get("/beta/{key}/api/state", self.state)
        app.router.add_post("/beta/{key}/api/action", self.action)
        app.router.add_get("/beta/{key}/media/{fid}", self.media)
