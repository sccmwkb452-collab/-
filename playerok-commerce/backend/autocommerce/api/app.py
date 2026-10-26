"""FastAPI application for the web panel.

Only the owner's panel talks to this API (via the Next.js rewrite on the same
origin). It never starts the Telegram bot or background work: those are the
separate ``bot`` and ``worker`` processes.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from .. import __version__
from ..config import ensure_startup_config, get_settings
from ..database.session import check_database, get_sessionmaker
from ..logging_setup import setup_logging
from ..services import health
from ..shared.errors import DomainError
from .routes import admin, auth, automation, catalog, insights, listings, messages, orders, suppliers
from .security import client_ip, limiter

log = logging.getLogger("autocommerce.api")


def error_body(code: str, message: str, **details) -> dict:
    return {"error": {"code": code, "message": message, **({"details": details} if details else {})}}


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="PlayerOK Auto Commerce API",
        version=__version__,
        docs_url=None if settings.is_production else "/api/docs",
        openapi_url=None if settings.is_production else "/api/openapi.json",
        redoc_url=None,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        started = time.perf_counter()
        if request.url.path.startswith("/api/v1/") and not request.url.path.startswith("/api/v1/health"):
            try:
                limiter.check(f"ip:{client_ip(request)}", settings.rate_limit_per_minute, 60)
            except DomainError as exc:
                return JSONResponse(error_body(exc.code, exc.message, **exc.details), status_code=exc.status_code)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        elapsed = (time.perf_counter() - started) * 1000
        if response.status_code >= 500 or elapsed > 3000:
            log.warning(
                "slow or failed request",
                extra={"path": request.url.path, "status": response.status_code, "ms": round(elapsed), "request_id": request_id},
            )
        return response

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message, **exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()][:20]
        return JSONResponse(error_body("validation_error", "Проверьте введённые данные", fields=fields), status_code=422)

    @app.exception_handler(StaleDataError)
    async def stale(_: Request, exc: StaleDataError) -> JSONResponse:
        return JSONResponse(error_body("conflict", "Данные изменились одновременно в другом окне. Обновите и повторите."), status_code=409)

    @app.exception_handler(IntegrityError)
    async def integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        log.info("integrity error", extra={"error": str(exc.orig)[:300]})
        return JSONResponse(error_body("conflict", "Такая запись уже существует или нарушает ограничения данных"), status_code=409)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", extra={"path": request.url.path})
        return JSONResponse(error_body("internal", "Внутренняя ошибка сервера. Подробности — в логах."), status_code=500)

    @app.get("/api/v1/health")
    async def liveness() -> dict:
        return {"ok": True, "service": "api", "version": __version__}

    @app.get("/api/v1/health/ready")
    async def readiness() -> JSONResponse:
        db_ok, message = await check_database()
        if not db_ok:
            return JSONResponse({"ok": False, "database": message}, status_code=503)
        async with get_sessionmaker()() as session:
            status = await health.status(session)
        public = {
            k: (v["ok"] if isinstance(v, dict) and "ok" in v else None) for k, v in status.items() if k in ("database", "worker", "bot")
        }
        return JSONResponse({"ok": True, **public, "mode": status.get("mode")}, status_code=200)

    for module in (auth, admin, catalog, orders, messages, listings, suppliers, insights, automation):
        app.include_router(module.router, prefix="/api/v1")
    return app


def build() -> FastAPI:
    setup_logging("api")
    ensure_startup_config("api")
    return create_app()


app = build()
