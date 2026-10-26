"""Auto-settings and the image generator."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...database.models import ListingImage
from ...imaging import templates as image_templates
from ...services import autosettings, catalog, listings
from ...shared.errors import DomainError, NotFound
from ..deps import Context, need

router = APIRouter(tags=["automation"])


@router.get("/autosettings")
async def overview(ctx: Context = Depends(need("view"))) -> dict:
    from ...services import app_settings

    return {"items": await autosettings.overview(ctx.session), "kill_switch": await app_settings.kill_switch(ctx.session)}


@router.get("/autosettings/{code}")
async def details(code: str, ctx: Context = Depends(need("view"))) -> dict:
    return await autosettings.details(ctx.session, code)


class ConfigIn(BaseModel):
    values: dict[str, Any]


@router.put("/autosettings/{code}")
async def save(code: str, body: ConfigIn, ctx: Context = Depends(need("autosettings.manage"))) -> dict:
    await autosettings.update(ctx.session, code, body.values, ctx.actor)
    return await autosettings.details(ctx.session, code)


class ToggleIn(BaseModel):
    enabled: bool


@router.post("/autosettings/{code}/toggle")
async def toggle(code: str, body: ToggleIn, ctx: Context = Depends(need("autosettings.manage"))) -> dict:
    await autosettings.set_enabled(ctx.session, code, body.enabled, ctx.actor)
    return await autosettings.details(ctx.session, code)


@router.post("/autosettings/{code}/reset")
async def reset(code: str, ctx: Context = Depends(need("autosettings.manage"))) -> dict:
    await autosettings.reset(ctx.session, code, ctx.actor)
    return await autosettings.details(ctx.session, code)


@router.post("/autosettings/{code}/test")
async def test(code: str, ctx: Context = Depends(need("view"))) -> dict:
    return await autosettings.test(ctx.session, code, ctx.actor)


class PreviewIn(BaseModel):
    field: str | None = Field(default=None, max_length=48)


@router.post("/autosettings/{code}/preview")
async def preview(code: str, body: PreviewIn, ctx: Context = Depends(need("view"))) -> dict:
    return {"text": await autosettings.preview(ctx.session, code, body.field)}


class EmergencyIn(BaseModel):
    reason: str = Field(default="Аварийное отключение из панели", max_length=300)


@router.post("/autosettings-emergency-off")
async def emergency(body: EmergencyIn, ctx: Context = Depends(need("security.manage"))) -> dict:
    count = await autosettings.emergency_disable_all(ctx.session, ctx.actor, body.reason)
    return {"disabled": count}


@router.get("/images/templates")
async def templates(ctx: Context = Depends(need("view"))) -> dict:
    rows = await image_templates.list_templates(ctx.session)
    return {
        "items": [
            {
                "code": t.code,
                "name": t.name,
                "kind": t.kind,
                "groups": t.category_groups,
                "width": t.width,
                "height": t.height,
                "active": t.active,
                "fields": [f["name"] for f in t.spec.get("fields", [])],
                "analysis": t.spec.get("analysis"),
            }
            for t in rows
        ],
        "originals_dir": "backend/assets/templates/originals",
    }


@router.get("/images/templates/{code}/file")
async def template_file(code: str, ctx: Context = Depends(need("view"))) -> FileResponse:
    from ...database.models import ImageTemplate

    tpl = (await ctx.session.execute(select(ImageTemplate).where(ImageTemplate.code == code))).scalar_one_or_none()
    if tpl is None:
        raise NotFound("Шаблон не найден")
    root = image_templates.templates_dir().resolve()
    path = (root / tpl.base_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise NotFound("Файл шаблона ещё не загружен")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=300"})


@router.post("/images/templates/sync")
async def sync_templates(ctx: Context = Depends(need("listings.manage"))) -> dict:
    return await image_templates.sync_registry(ctx.session)


class PreviewImageIn(BaseModel):
    product_id: int
    template_code: str | None = Field(default=None, max_length=64)
    listing_id: int | None = None
    overrides: dict[str, str] = Field(default_factory=dict)
    show_price: bool = True


def image_out(image: ListingImage) -> dict:
    return {
        "id": image.id,
        "product_id": image.product_id,
        "listing_id": image.listing_id,
        "version": image.listing_version,
        "template": image.template_code,
        "width": image.width,
        "height": image.height,
        "url": f"/api/v1/images/{image.id}/file",
        "preview": image.is_preview,
        "created_at": image.created_at.isoformat() if image.created_at else None,
    }


@router.post("/images/generate")
async def generate(body: PreviewImageIn, ctx: Context = Depends(need("listings.manage"))) -> dict:
    product = await catalog.get_product(ctx.session, body.product_id)
    listing = await listings.get_listing(ctx.session, body.listing_id) if body.listing_id else None
    if listing is not None and listing.product_id != product.id:
        raise DomainError("Объявление относится к другому товару")
    price = (listing.price if listing else product.recommended_price) if body.show_price else None
    image = await image_templates.generate_for_product(
        ctx.session,
        product,
        template_code=body.template_code,
        listing_id=listing.id if listing else None,
        listing_version=listing.version if listing else None,
        price=price,
        overrides=body.overrides,
        preview=listing is None,
    )
    return image_out(image)


class BatchIn(BaseModel):
    product_ids: list[int] = Field(min_length=1, max_length=100)
    template_code: str | None = Field(default=None, max_length=64)


@router.post("/images/batch")
async def batch(body: BatchIn, ctx: Context = Depends(need("listings.manage"))) -> dict:
    results: dict[str, Any] = {"ok": [], "errors": {}}
    for pid in body.product_ids:
        try:
            product = await catalog.get_product(ctx.session, pid)
            image = await image_templates.generate_for_product(
                ctx.session, product, template_code=body.template_code, price=product.recommended_price, preview=True
            )
            results["ok"].append(image_out(image))
        except (DomainError, NotFound) as exc:
            results["errors"][str(pid)] = exc.message
    return results


@router.get("/images")
async def list_images(product_id: int | None = None, ctx: Context = Depends(need("view"))) -> dict:
    stmt = select(ListingImage).order_by(ListingImage.id.desc()).limit(60)
    if product_id:
        stmt = stmt.where(ListingImage.product_id == product_id)
    return {"items": [image_out(i) for i in (await ctx.session.execute(stmt)).scalars()]}


@router.get("/images/{image_id}/file")
async def image_file(image_id: int, ctx: Context = Depends(need("view"))) -> FileResponse:
    image = await ctx.session.get(ListingImage, image_id)
    if image is None:
        raise NotFound("Изображение не найдено")
    path = image_templates.image_path(image)
    if not path.exists():
        raise NotFound("Файл изображения отсутствует")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
