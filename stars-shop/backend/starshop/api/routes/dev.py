"""Development helper: signs initData so the Mini App can be opened in a
plain browser. Mounted only when APP_ENV=development and DEV_AUTH_ENABLED=true."""

from __future__ import annotations

import time

from fastapi import APIRouter, Query

from ...config import get_settings
from ...shared.telegram_auth import sign_init_data

router = APIRouter(prefix="/dev")


@router.get("/init-data")
async def dev_init_data(
    telegram_id: int = Query(default=100001, gt=0),
    username: str = Query(default="demo_user", max_length=32),
    first_name: str = Query(default="Demo", max_length=64),
    start_param: str | None = Query(default=None, max_length=64),
) -> dict:
    fields = {
        "query_id": "dev",
        "user": {"id": telegram_id, "first_name": first_name, "username": username, "language_code": "ru", "allows_write_to_pm": True},
        "auth_date": int(time.time()),
    }
    if start_param:
        fields["start_param"] = start_param
    return {"init_data": sign_init_data(fields, get_settings().bot_token.get_secret_value())}
