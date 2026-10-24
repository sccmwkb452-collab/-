"""Errors reported by the Mini App, shown in Admin → Ошибки."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from ...services import errors
from ..deps import ip_rate_limit
from ..schemas import Strict

router = APIRouter()


class ClientErrorIn(Strict):
    kind: str = Field(default="error", max_length=32)
    message: str = Field(max_length=500)
    path: str | None = Field(default=None, max_length=256)
    stack: str | None = Field(default=None, max_length=4000)


@router.post("/client-errors", status_code=204, dependencies=[Depends(ip_rate_limit("client_errors", 20))])
async def client_error(body: ClientErrorIn, request: Request) -> None:
    await errors.record(
        "client",
        f"{body.kind}: {body.message}",
        path=body.path,
        details={"stack": body.stack, "user_agent": (request.headers.get("user-agent") or "")[:200]},
    )
