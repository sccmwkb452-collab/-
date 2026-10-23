from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from ...delivery import service as delivery_service
from ...delivery.base import DeliveryError
from ...payments import service as payments
from ...shared.errors import AppError, NotFound, Unauthorized
from ..deps import RuntimeDep, SessionDep, client_ip, ip_rate_limit

router = APIRouter(prefix="/webhooks")
log = logging.getLogger(__name__)
MAX_BODY = 256 * 1024


async def _body(request: Request) -> bytes:
    body = await request.body()
    if len(body) > MAX_BODY:
        raise AppError("payload too large", code="payload_too_large")
    return body


@router.post("/payments/{provider}", dependencies=[Depends(ip_rate_limit("webhook", 600))])
async def payment_webhook(provider: str, request: Request, session: SessionDep, runtime: RuntimeDep) -> dict:
    body = await _body(request)
    try:
        result = await payments.handle_webhook(session, provider, dict(request.headers), body, client_ip(request), runtime)
        await session.commit()
        return result
    except (Unauthorized, NotFound):
        raise
    except AppError:
        await session.rollback()
        raise
    except Exception as exc:
        # Roll back everything (including the de-dup row) so the provider's
        # retry is processed normally; keep a trace for the admin panel.
        await session.rollback()
        log.exception("webhook processing failed", extra={"provider": provider})
        await payments.log_failed_webhook(provider, body, client_ip(request), f"{exc.__class__.__name__}: {exc}")
        raise


@router.post("/delivery/{provider}", dependencies=[Depends(ip_rate_limit("delivery_webhook", 600))])
async def delivery_webhook(provider: str, request: Request, session: SessionDep) -> dict:
    body = await _body(request)
    try:
        result = await delivery_service.handle_callback(session, provider, dict(request.headers), body)
    except DeliveryError as exc:
        await session.rollback()
        if exc.code == "signature_invalid":
            raise Unauthorized("invalid signature", code="signature_invalid") from None
        raise
    except KeyError:
        raise NotFound("unknown provider") from None
    await session.commit()
    return {"ok": True, "result": result}
