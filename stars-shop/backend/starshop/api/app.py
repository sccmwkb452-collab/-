from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..config import get_settings
from ..database.session import dispose_engine, session_scope
from ..logging_setup import setup_logging
from ..services.admin_auth import ensure_bootstrap_admins
from ..shared.errors import AppError, RateLimited
from .ratelimit import get_limiter
from .routes import demo, dev, me, orders, public, support, webhooks
from .routes.admin import audit as admin_audit
from .routes.admin import auth as admin_auth
from .routes.admin import catalog as admin_catalog
from .routes.admin import dashboard as admin_dashboard
from .routes.admin import orders as admin_orders
from .routes.admin import promo as admin_promo
from .routes.admin import settings as admin_settings
from .routes.admin import support as admin_support
from .routes.admin import users as admin_users

log = logging.getLogger("starshop.api")
RATE_LIMIT_EXEMPT = ("/api/health", "/api/v1/webhooks/")


def _error(status: int, code: str, message: str, details=None, request_id: str | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    if request_id:
        body["error"]["request_id"] = request_id
    return JSONResponse(status_code=status, content=body)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging("api")
    async with session_scope() as session:
        await ensure_bootstrap_admins(session)
    log.info("api started", extra={"env": get_settings().app_env})
    yield
    await get_limiter().close()
    await dispose_engine()


def create_app(*, lifespan_handler=lifespan) -> FastAPI:
    settings = get_settings()
    dev_mode = settings.app_env == "development"
    app = FastAPI(
        title=f"{settings.brand_name} Stars Shop API",
        version="1.0.0",
        lifespan=lifespan_handler,
        docs_url="/api/docs" if dev_mode else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if dev_mode else None,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-CSRF-Token"],
            max_age=600,
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        path = request.url.path
        if path.startswith("/api") and not path.startswith(RATE_LIMIT_EXEMPT):
            ip = request.client.host if request.client else "unknown"
            if not await get_limiter().hit(f"ip:{ip}", settings.rate_limit_per_ip_per_minute, 60):
                exc = RateLimited()
                return _error(exc.status_code, exc.code, exc.message, request_id=request_id)
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["X-Content-Type-Options"] = "nosniff"
        if path != "/api/health":
            log.info(
                "request",
                extra={"method": request.method, "path": path, "status": response.status_code, "ms": elapsed, "request_id": request_id},
            )
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        if exc.status_code >= 500:
            log.warning("app error", extra={"code": exc.code, "msg_text": exc.message, "path": request.url.path})
        return _error(exc.status_code, exc.code, exc.message, exc.details, getattr(request.state, "request_id", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [{"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()][:20]
        return _error(422, "validation_error", "Проверьте введённые данные", details, getattr(request.state, "request_id", None))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _error(exc.status_code, code, str(exc.detail), request_id=getattr(request.state, "request_id", None))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", None)
        log.exception("unhandled error", extra={"path": request.url.path, "request_id": request_id})
        return _error(500, "internal_error", "Что-то пошло не так. Мы уже разбираемся", request_id=request_id)

    v1 = APIRouter(prefix="/api/v1")
    for module in (public, me, orders, support, webhooks, demo):
        v1.include_router(module.router)
    if dev_mode and settings.dev_auth_enabled:
        v1.include_router(dev.router)

    admin = APIRouter(prefix="/admin")
    for module in (
        admin_auth,
        admin_dashboard,
        admin_catalog,
        admin_orders,
        admin_users,
        admin_promo,
        admin_settings,
        admin_support,
        admin_audit,
    ):
        admin.include_router(module.router)
    v1.include_router(admin)

    app.include_router(v1)
    app.include_router(public.health_router, prefix="/api")
    return app


app = create_app()
