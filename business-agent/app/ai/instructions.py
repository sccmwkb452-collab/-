"""Глобальные инструкции ИИ: анализ, подтверждение, версии и откат.

Изменять конфигурацию может только администратор (проверка по Telegram ID — в хендлерах
и здесь же, повторно). Изменения хранятся отдельно от истории переписок.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import LLMClient
from app.ai.prompts import INSTRUCTION_SYSTEM
from app.ai.schemas import INSTRUCTION_ANALYSIS_SCHEMA
from app.ai.validation import find_bot_mentions
from app.core.audit import audit
from app.db.models import AdminMaterial, AIConfigVersion, PendingInstruction, TradeBotConfig

CONFIG_FIELDS = ("instructions", "style", "negotiation_rules", "trading_rules", "examples")


class NotAdminError(PermissionError):
    pass


@dataclass
class AdminInput:
    text: str
    materials: list[AdminMaterial]  # уже проанализированные медиа


def ensure_admin(settings, telegram_id: int | None) -> None:
    if not settings.is_admin(telegram_id):
        raise NotAdminError("Только администратор может менять глобальные инструкции ИИ")


async def get_active_config(session: AsyncSession) -> AIConfigVersion | None:
    return await session.scalar(select(AIConfigVersion).where(AIConfigVersion.is_active.is_(True)))


def config_to_dict(cfg: AIConfigVersion | None) -> dict[str, Any]:
    if cfg is None:
        return {f: ([] if f == "examples" else "") for f in CONFIG_FIELDS}
    return {f: getattr(cfg, f) for f in CONFIG_FIELDS}


async def analyze_instruction(
    session: AsyncSession, llm: LLMClient, settings, admin_id: int, data: AdminInput
) -> PendingInstruction:
    ensure_admin(settings, admin_id)
    current = await get_active_config(session)
    materials_desc = [
        {
            "material_id": m.id,
            "kind": m.kind,
            "caption": m.text,
            "analysis": m.analysis or {"ok": False, "error": "не проанализировано"},
        }
        for m in data.materials
    ]
    content = [
        {
            "type": "text",
            "text": "<current_config>\n"
            + json.dumps(config_to_dict(current), ensure_ascii=False, indent=1)
            + "\n</current_config>\n\n<admin_instruction>\n"
            + (data.text or "(без текста)")
            + "\n</admin_instruction>\n\n<materials>\n"
            + json.dumps(materials_desc, ensure_ascii=False, indent=1)
            + "\n</materials>",
        }
    ]
    analysis = await llm.generate_json(system=INSTRUCTION_SYSTEM, content=content, schema=INSTRUCTION_ANALYSIS_SCHEMA, effort="high")
    analysis["code_checks"] = await _code_checks(session, analysis.get("proposed") or {})
    pending = PendingInstruction(
        admin_telegram_id=admin_id,
        source_kinds=sorted({m.kind for m in data.materials} | ({"text"} if data.text else set())),
        analysis=analysis,
    )
    session.add(pending)
    await session.flush()
    for m in data.materials:
        m.pending_instruction_id = pending.id
    await audit(session, "ai_instruction_analyzed", actor="admin", pending_id=pending.id,
                instruction_type=analysis.get("instruction_type"), conflicts=len(analysis.get("conflicts") or []))
    return pending


async def _code_checks(session: AsyncSession, proposed: dict[str, Any]) -> list[str]:
    """Проверки, не зависящие от ИИ: упоминания ботов вне реестра торговых ботов."""
    known = set((await session.scalars(select(TradeBotConfig.bot_username))).all())
    text = " ".join(str(proposed.get(f, "")) for f in CONFIG_FIELDS)
    unknown = find_bot_mentions(text) - known
    checks = []
    if unknown:
        checks.append(
            "В инструкциях упомянуты боты вне реестра торговых ботов: "
            + ", ".join("@" + b for b in sorted(unknown))
            + ". Они НЕ станут разрешёнными для сделок — разрешённый бот задаётся только в разделе «Торговый бот»."
        )
    return checks


async def _next_version(session: AsyncSession) -> int:
    return (await session.scalar(select(func.max(AIConfigVersion.version))) or 0) + 1


async def _activate(session: AsyncSession, values: dict[str, Any], admin_id: int, note: str, based_on: int | None) -> AIConfigVersion:
    await session.execute(update(AIConfigVersion).values(is_active=False))
    cfg = AIConfigVersion(
        version=await _next_version(session),
        is_active=True,
        created_by=admin_id,
        note=note[:2000],
        based_on_version=based_on,
        instructions=str(values.get("instructions") or ""),
        style=str(values.get("style") or ""),
        negotiation_rules=str(values.get("negotiation_rules") or ""),
        trading_rules=str(values.get("trading_rules") or ""),
        examples=list(values.get("examples") or []),
    )
    session.add(cfg)
    await session.flush()
    return cfg


async def apply_pending(session: AsyncSession, settings, admin_id: int, pending_id: int) -> AIConfigVersion:
    ensure_admin(settings, admin_id)
    pending = await session.get(PendingInstruction, pending_id)
    if pending is None or pending.status != "pending":
        raise ValueError("Предложение не найдено или уже обработано")
    current = await get_active_config(session)
    cfg = await _activate(
        session,
        pending.analysis.get("proposed") or {},
        admin_id,
        note=pending.analysis.get("summary", ""),
        based_on=current.version if current else None,
    )
    pending.status = "applied"
    await audit(session, "ai_config_applied", actor="admin", version=cfg.version, pending_id=pending.id)
    return cfg


async def reject_pending(session: AsyncSession, settings, admin_id: int, pending_id: int) -> None:
    ensure_admin(settings, admin_id)
    pending = await session.get(PendingInstruction, pending_id)
    if pending and pending.status == "pending":
        pending.status = "rejected"
        await audit(session, "ai_config_rejected", actor="admin", pending_id=pending.id)


async def rollback_to(session: AsyncSession, settings, admin_id: int, version: int) -> AIConfigVersion:
    """Откат = новая версия с содержимым старой (история не переписывается)."""
    ensure_admin(settings, admin_id)
    target = await session.scalar(select(AIConfigVersion).where(AIConfigVersion.version == version))
    if target is None:
        raise ValueError(f"Версия {version} не найдена")
    cfg = await _activate(session, config_to_dict(target), admin_id, note=f"Откат к версии {version}", based_on=version)
    await audit(session, "ai_config_rollback", actor="admin", to_version=version, new_version=cfg.version)
    return cfg


async def list_versions(session: AsyncSession, limit: int = 10) -> list[AIConfigVersion]:
    return list(
        (await session.scalars(select(AIConfigVersion).order_by(AIConfigVersion.version.desc()).limit(limit))).all()
    )

