"""HTTP endpoint for provider notifications and a health check."""

from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from payments.base import ProviderError
from payments.service import PaymentService
from services.errors import ShopError

log = logging.getLogger(__name__)

MAX_BODY = 64 * 1024


def build_app(service: PaymentService) -> web.Application:
    app = web.Application(client_max_size=MAX_BODY)

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def notify(request: web.Request) -> web.Response:
        if request.match_info["provider"] != service.provider.name:
            return web.json_response({"ok": False}, status=404)
        body = await request.read()
        try:
            external_id = await service.provider.parse_webhook(body, request.headers)
        except ProviderError as exc:
            log.warning("rejected webhook: %s", exc)
            return web.json_response({"ok": False}, status=400)
        except ValueError:
            return web.json_response({"ok": False}, status=400)
        if external_id:
            try:
                result = await service.check_by_external(external_id)
            except ShopError as exc:
                log.warning("webhook check failed: %s", exc.message)
                return web.json_response({"ok": False}, status=503)  # provider will retry
            if result is None:
                log.warning("webhook for unknown invoice")
        return web.json_response({"ok": True})

    app.router.add_get("/healthz", health)
    app.router.add_post("/payments/{provider}", notify)
    return app


async def poll_forever(service: PaymentService, interval: int) -> None:
    while True:
        try:
            credited = await service.poll_pending()
            if credited:
                log.info("poller credited %s payment(s)", credited)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("payment poller iteration failed")
        await asyncio.sleep(interval)
