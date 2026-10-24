"""Admin → Кнопки бота: extra buttons of the bot's main menu."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import func, select

from ....database.enums import BotButtonAction, ButtonStyle
from ....database.models import BotButton
from ....services import audit, bot_buttons
from ....shared.errors import Conflict, NotFound
from ...deps import ManagerAdmin, SessionDep, SupportAdmin
from ...schemas import Strict

router = APIRouter(prefix="/bot-buttons")


class BotButtonIn(Strict):
    title: str = Field(min_length=1, max_length=48)
    emoji: str | None = Field(default=None, max_length=16)
    row: int = Field(default=0, ge=0, lt=20)
    position: int = Field(default=0, ge=0, lt=20)
    is_active: bool = True
    action: BotButtonAction
    style: ButtonStyle | None = None
    text: str | None = Field(default=None, max_length=2000)
    url: str | None = Field(default=None, max_length=512)
    section: str | None = Field(default=None, max_length=32)
    product_id: int | None = None


async def _get(session, button_id: int) -> BotButton:
    button = await session.get(BotButton, button_id)
    if button is None:
        raise NotFound("Кнопка не найдена", code="bot_button_not_found")
    return button


@router.get("")
async def list_buttons(ctx: SupportAdmin, session: SessionDep) -> dict:
    rows = await session.execute(select(BotButton).order_by(BotButton.row, BotButton.position, BotButton.id))
    return {"items": [bot_buttons.serialize(b) for b in rows.scalars()], "options": bot_buttons.options()}


@router.post("", status_code=201)
async def create_button(body: BotButtonIn, ctx: ManagerAdmin, session: SessionDep) -> dict:
    count = await session.scalar(select(func.count()).select_from(BotButton)) or 0
    if count >= bot_buttons.MAX_BUTTONS:
        raise Conflict(f"Не больше {bot_buttons.MAX_BUTTONS} кнопок", code="bot_buttons_limit")
    button = BotButton(**await bot_buttons.normalize(session, body.model_dump()))
    session.add(button)
    await session.flush()
    await session.refresh(button)
    after = bot_buttons.serialize(button)
    await audit.record(session, ctx.admin, "bot_button.create", entity_type="bot_button", entity_id=button.id, after=after, meta=ctx.meta)
    await session.commit()
    return after


@router.put("/{button_id}")
async def update_button(button_id: int, body: BotButtonIn, ctx: ManagerAdmin, session: SessionDep) -> dict:
    button = await _get(session, button_id)
    before = bot_buttons.serialize(button)
    for key, value in (await bot_buttons.normalize(session, body.model_dump())).items():
        setattr(button, key, value)
    await session.flush()
    await session.refresh(button)
    after = bot_buttons.serialize(button)
    await audit.record(
        session, ctx.admin, "bot_button.update", entity_type="bot_button", entity_id=button.id, before=before, after=after, meta=ctx.meta
    )
    await session.commit()
    return after


@router.delete("/{button_id}")
async def delete_button(button_id: int, ctx: ManagerAdmin, session: SessionDep) -> dict:
    button = await _get(session, button_id)
    before = bot_buttons.serialize(button)
    await session.delete(button)
    await audit.record(session, ctx.admin, "bot_button.delete", entity_type="bot_button", entity_id=button_id, before=before, meta=ctx.meta)
    await session.commit()
    return {"ok": True}
