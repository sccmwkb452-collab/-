"""«Автонастройки»: the 14 automation items of the settings menu.

Each item declares which marketplace capabilities it needs. With the current
PlayerOK integration (manual mode, no API) items either work in
*operator-assist* mode — the system prepares the text or reminder and sends it
to the operator — or are shown as «Интеграция недоступна» with the reason.
Nothing pretends to act on PlayerOK.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import LogResult
from ..database.models import AutomationLog, AutoSetting
from ..integrations.marketplace.base import CAPABILITY_LABELS
from ..integrations.marketplace.playerok_manual import get_marketplace
from ..shared.errors import DomainError, NotFound
from ..shared.timeutil import utcnow
from . import app_settings
from . import templates as tpl
from .audit import Actor, audit, automation_log


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    type: str  # text | template | bool | int | choice | multichoice | list
    help: str = ""
    choices: tuple[tuple[str, str], ...] = ()
    min: int | None = None
    max: int | None = None


@dataclass(frozen=True)
class Feature:
    code: str
    emoji: str
    title: str
    description: str
    requires: tuple[str, ...]
    assist: str | None  # what works without the capabilities (operator-assist), None — nothing
    fields: tuple[Field, ...]
    defaults: dict[str, Any] = field(default_factory=dict)
    preview_field: str | None = None
    safety: str = ""

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.title}"


CATEGORY_GROUPS = (
    ("telegram", "Telegram"),
    ("promotion", "Продвижение"),
    ("steam", "Steam"),
    ("giftcards", "Подарочные карты"),
    ("games", "Игры"),
    ("roblox", "Roblox"),
    ("subscriptions", "Подписки"),
)

FEATURES: tuple[Feature, ...] = (
    Feature(
        "greeting",
        "👋",
        "Приветствие",
        "Приветственное сообщение покупателю при первом обращении.",
        ("fetch_messages", "send_messages"),
        "Когда вы записываете первое сообщение покупателя, бот присылает готовое приветствие с кнопкой «Скопировать».",
        (
            Field("text", "Текст приветствия", "template"),
            Field("only_first", "Только при первом сообщении", "bool"),
            Field("cooldown_hours", "Повторно не раньше, ч", "int", min=1, max=720),
        ),
        {"text": "Здравствуйте, {buyer}! Спасибо, что выбрали {shop}. Отвечу в ближайшее время.", "only_first": True, "cooldown_hours": 24},
        preview_field="text",
    ),
    Feature(
        "auto_confirm",
        "🤝",
        "Автоподтверждение",
        "Подтверждение операций, для которых это разрешено правилами PlayerOK и безопасно.",
        ("confirm_deals",),
        None,
        (
            Field("categories", "Категории", "multichoice", choices=CATEGORY_GROUPS),
            Field("only_after_delivery", "Только после выдачи товара", "bool"),
            Field("min_hours_after_delivery", "Не раньше чем через, ч", "int", min=1, max=168),
            Field("exceptions", "Исключения (артикулы)", "list"),
            Field("require_manual", "Требовать ручное подтверждение", "bool"),
        ),
        {"categories": [], "only_after_delivery": True, "min_hours_after_delivery": 24, "exceptions": [], "require_manual": True},
        safety="Сделка не подтверждается автоматически, если это может лишить продавца или покупателя защиты.",
    ),
    Feature(
        "auto_raise",
        "🚀",
        "Автоподнятие лотов",
        "Поднятие объявлений по расписанию.",
        ("raise_listings",),
        "По расписанию бот напоминает, какие объявления пора поднять вручную.",
        (
            Field("interval_minutes", "Интервал, мин", "int", min=30, max=10080),
            Field("categories", "Категории", "multichoice", choices=CATEGORY_GROUPS),
            Field("listing_ids", "Объявления (ID)", "list"),
            Field("max_budget_rub", "Максимальный бюджет, ₽", "int", min=0, max=1_000_000),
            Field("max_operations_per_day", "Лимит операций в сутки", "int", min=1, max=500),
        ),
        {"interval_minutes": 240, "categories": [], "listing_ids": [], "max_budget_rub": 0, "max_operations_per_day": 6},
    ),
    Feature(
        "auto_listing",
        "🔄",
        "Автовыставление лотов",
        "Создание объявлений из выгодных позиций поставщиков.",
        ("publish_listings",),
        "Система сама готовит объявления (текст, цена, изображение) и присылает их на подтверждение; публикуете вы.",
        (
            Field("sources", "Источники товаров (коды поставщиков)", "list"),
            Field("categories", "Категории", "multichoice", choices=CATEGORY_GROUPS),
            Field("description_template", "Шаблон описания", "choice", choices=(("auto", "По категории"), ("default", "Универсальный"))),
            Field("image_template", "Шаблон изображения", "text"),
            Field(
                "price_strategy",
                "Ценовая стратегия",
                "choice",
                choices=(("recommended", "Рекомендуемая"), ("target", "Целевая"), ("min", "Минимальная")),
            ),
            Field("min_profit_rub", "Минимальная прибыль, ₽", "int", min=0, max=1_000_000),
            Field("max_listings", "Максимум объявлений", "int", min=1, max=1000),
            Field("publish_mode", "Публикация", "choice", choices=(("confirm", "После подтверждения"), ("auto", "Автоматически"))),
            Field("relist", "Выставлять повторно после продажи", "bool"),
            Field("stop_on_low_margin", "Останавливать при недостаточной марже", "bool"),
        ),
        {
            "sources": [],
            "categories": [],
            "description_template": "auto",
            "image_template": "",
            "price_strategy": "recommended",
            "min_profit_rub": 50,
            "max_listings": 20,
            "publish_mode": "confirm",
            "relist": True,
            "stop_on_low_margin": True,
        },
    ),
    Feature(
        "auto_delivery",
        "📦",
        "Автовыдача",
        "Резервирование и выдача цифровых товаров после оплаты.",
        ("send_messages",),
        "Код резервируется автоматически (без повторной выдачи), а вам приходит готовое сообщение покупателю с кнопкой «Показать код».",
        (
            Field("categories", "Категории", "multichoice", choices=CATEGORY_GROUPS),
            Field(
                "code_source", "Источник кодов", "choice", choices=(("inventory", "Склад кодов"), ("supplier", "Склад, затем поставщик"))
            ),
            Field("instruction", "Инструкция покупателю", "template"),
            Field("delay_seconds", "Задержка перед выдачей, с", "int", min=0, max=3600),
            Field("check_stock", "Проверять наличие", "bool"),
            Field("mode", "Выдача", "choice", choices=(("auto", "Автоматически"), ("operator", "После подтверждения оператором"))),
        ),
        {
            "categories": [],
            "code_source": "supplier",
            "instruction": "Ваш код: {instructions}\nЗаказ {order_number}. Если возникнут вопросы — напишите сюда, поможем.",
            "delay_seconds": 0,
            "check_stock": True,
            "mode": "operator",
        },
        preview_field="instruction",
        safety="Резерв кода и проверка повторной выдачи включены всегда и не отключаются.",
    ),
    Feature(
        "autoresponder",
        "🤖",
        "Автоответчик",
        "Правила «условие → действие» для сообщений покупателей.",
        ("fetch_messages", "send_messages"),
        "Для записанных сообщений бот подбирает ответ по правилам и присылает его вам с кнопкой «Скопировать».",
        (
            Field(
                "fallback",
                "Если вопрос не распознан",
                "choice",
                choices=(("manual", "Передать оператору"), ("neutral", "Нейтральный ответ")),
            ),
            Field("neutral_text", "Нейтральный ответ", "template"),
        ),
        {"fallback": "manual", "neutral_text": "Здравствуйте! Получили ваше сообщение, ответим в ближайшее время."},
        preview_field="neutral_text",
        safety="Ответ, утверждающий, что заказ выполнен, не отправляется, пока заказ не выдан на самом деле.",
    ),
    Feature(
        "confirm_reminder",
        "⏰",
        "Напоминание о подтверждении",
        "Напоминание покупателю подтвердить получение после выдачи.",
        ("send_messages",),
        "Когда наступает срок, бот присылает вам текст напоминания для покупателя.",
        (
            Field("text", "Текст", "template"),
            Field("delay_hours", "Через сколько часов после выдачи", "int", min=1, max=168),
            Field("max_count", "Максимум напоминаний", "int", min=1, max=3),
            Field("interval_hours", "Интервал между напоминаниями, ч", "int", min=1, max=168),
        ),
        {
            "text": "Здравствуйте, {buyer}! Заказ {order_number} выдан. Если всё в порядке, подтвердите, пожалуйста, получение на PlayerOK.",
            "delay_hours": 6,
            "max_count": 2,
            "interval_hours": 24,
        },
        preview_field="text",
    ),
    Feature(
        "review_reminder",
        "⭐",
        "Напоминание об отзыве",
        "Одна вежливая просьба оставить отзыв после завершения сделки.",
        ("send_messages",),
        "Через заданное время бот присылает вам текст просьбы об отзыве. После отзыва напоминаний нет.",
        (Field("text", "Текст", "template"), Field("delay_hours", "Через сколько часов после завершения", "int", min=1, max=336)),
        {"text": "Спасибо за покупку, {buyer}! Если вам понравилось, будем рады отзыву о заказе {order_number}.", "delay_hours": 12},
        preview_field="text",
        safety="Только одно напоминание, без давления и без повторов после отзыва.",
    ),
    Feature(
        "offline_text",
        "💤",
        "Текст, если не в сети",
        "Автоответ, когда оператор недоступен.",
        ("presence", "send_messages"),
        "Статус «в сети» на PlayerOK недоступен, поэтому используется расписание: сообщения, записанные вне рабочих часов, получают этот текст как подсказку.",
        (
            Field("text", "Текст", "template"),
            Field("offline_from", "Не в сети с (ЧЧ:ММ)", "text"),
            Field("offline_to", "Не в сети до (ЧЧ:ММ)", "text"),
        ),
        {
            "text": "Здравствуйте! Сейчас я не в сети, отвечу утром. Заказ {order_number} будет обработан.",
            "offline_from": "23:00",
            "offline_to": "09:00",
        },
        preview_field="text",
    ),
    Feature(
        "ignore_text",
        "💬",
        "Текст при игноре",
        "Сообщение, если на вопрос покупателя долго нет ответа.",
        ("fetch_messages", "send_messages"),
        "Если записанное сообщение остаётся без ответа дольше срока, бот напоминает вам и даёт готовый текст.",
        (Field("text", "Текст", "template"), Field("after_minutes", "Через сколько минут без ответа", "int", min=5, max=1440)),
        {"text": "Здравствуйте, {buyer}! Ваш вопрос не потерялся — ответим в ближайшее время.", "after_minutes": 30},
        preview_field="text",
    ),
    Feature(
        "review_texts",
        "💬",
        "Тексты после отзывов",
        "Ответы на положительные, нейтральные и отрицательные отзывы.",
        ("fetch_reviews", "send_messages"),
        "Когда вы вносите отзыв, бот подбирает ответ по оценке.",
        (
            Field("positive", "Положительный отзыв", "template"),
            Field("neutral", "Нейтральный отзыв", "template"),
            Field("negative", "Отрицательный отзыв", "template"),
        ),
        {
            "positive": "Спасибо за отзыв, {buyer}! Будем рады видеть вас снова.",
            "neutral": "Спасибо за отзыв, {buyer}! Расскажите, что можно улучшить — учтём.",
            "negative": "{buyer}, нам жаль, что так вышло. Напишите, пожалуйста, детали по заказу {order_number} — разберёмся.",
        },
        preview_field="positive",
    ),
    Feature(
        "problem_text",
        "💬",
        "Текст при проблеме",
        "Сообщение покупателю, если с заказом возникла проблема.",
        ("send_messages",),
        "При ошибке или споре по заказу бот присылает вам этот текст с подставленными данными.",
        (Field("text", "Текст", "template"),),
        {"text": "{buyer}, по заказу {order_number} («{product}») возникла задержка. {next_steps} Мы на связи."},
        preview_field="text",
    ),
    Feature(
        "seller_confirm_text",
        "💬",
        "Текст после вашего подтверждения",
        "Сообщение после того, как вы отметили заказ выданным.",
        ("send_messages",),
        "После отметки «Выдано» бот присылает вам этот текст для покупателя.",
        (Field("text", "Текст", "template"),),
        {"text": "{buyer}, заказ {order_number} выдан. {instructions} Проверьте, пожалуйста, и подтвердите получение."},
        preview_field="text",
    ),
    Feature(
        "buyer_confirm_text",
        "💬",
        "Текст после подтверждения клиентом",
        "Сообщение после подтверждения сделки покупателем.",
        ("send_messages",),
        "После отметки «Покупатель подтвердил» бот присылает вам этот текст.",
        (Field("text", "Текст", "template"),),
        {"text": "Спасибо, {buyer}! Сделка {order_number} завершена. Обращайтесь ещё."},
        preview_field="text",
    ),
)

BY_CODE: dict[str, Feature] = {f.code: f for f in FEATURES}


def feature(code: str) -> Feature:
    try:
        return BY_CODE[code]
    except KeyError as exc:
        raise NotFound("Нет такой автонастройки") from exc


def integration_state(f: Feature) -> dict[str, Any]:
    market = get_marketplace()
    missing = [c for c in f.requires if not market.supports(c)]
    if not missing:
        return {"state": "available", "label": "🟢 Интеграция доступна", "reason": "", "missing": []}
    reasons = [f"{CAPABILITY_LABELS[c]}: {market.reason(c)}" for c in missing]
    if f.assist:
        return {
            "state": "assist",
            "label": "🟡 Режим подсказок оператору",
            "reason": "\n".join(reasons),
            "assist": f.assist,
            "missing": missing,
        }
    return {"state": "unavailable", "label": "🔴 Интеграция недоступна", "reason": "\n".join(reasons), "missing": missing}


async def ensure_rows(session: AsyncSession) -> None:
    existing = {r.code for r in (await session.execute(select(AutoSetting))).scalars()}
    for f in FEATURES:
        if f.code not in existing:
            session.add(AutoSetting(code=f.code, enabled=False, config=copy.deepcopy(f.defaults)))
    await session.flush()


async def get_row(session: AsyncSession, code: str) -> AutoSetting:
    f = feature(code)
    row = await session.get(AutoSetting, code)
    if row is None:
        row = AutoSetting(code=code, enabled=False, config=copy.deepcopy(f.defaults))
        session.add(row)
        await session.flush()
    return row


def effective_config(f: Feature, row: AutoSetting) -> dict[str, Any]:
    cfg = copy.deepcopy(f.defaults)
    cfg.update({k: v for k, v in (row.config or {}).items() if k in cfg})
    return cfg


async def is_active(session: AsyncSession, code: str) -> tuple[bool, dict[str, Any]]:
    """(enabled and not stopped by the kill switch, config)."""
    f = feature(code)
    row = await get_row(session, code)
    if not row.enabled or await app_settings.automation_stopped(session):
        return False, effective_config(f, row)
    return True, effective_config(f, row)


async def overview(session: AsyncSession) -> list[dict[str, Any]]:
    rows = {r.code: r for r in (await session.execute(select(AutoSetting))).scalars()}
    stopped = await app_settings.automation_stopped(session)
    out = []
    for f in FEATURES:
        row = rows.get(f.code)
        enabled = bool(row and row.enabled)
        out.append(
            {
                "code": f.code,
                "label": f.label,
                "emoji": f.emoji,
                "title": f.title,
                "enabled": enabled,
                "stopped": stopped,
                "integration": integration_state(f),
                "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
            }
        )
    return out


async def details(session: AsyncSession, code: str) -> dict[str, Any]:
    f = feature(code)
    row = await get_row(session, code)
    history = (
        (await session.execute(select(AutomationLog).where(AutomationLog.feature == code).order_by(AutomationLog.id.desc()).limit(15)))
        .scalars()
        .all()
    )
    return {
        "code": f.code,
        "label": f.label,
        "title": f.title,
        "description": f.description,
        "safety": f.safety,
        "enabled": row.enabled,
        "stopped": await app_settings.automation_stopped(session),
        "integration": integration_state(f),
        "config": effective_config(f, row),
        "defaults": f.defaults,
        "fields": [
            {"name": x.name, "label": x.label, "type": x.type, "help": x.help, "choices": list(x.choices), "min": x.min, "max": x.max}
            for x in f.fields
        ],
        "variables": tpl.VARIABLES,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "updated_by": row.updated_by,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_error": row.last_error,
        "history": [
            {"at": h.created_at.isoformat(), "action": h.action, "result": h.result.value, "message": h.message, "order_id": h.order_id}
            for h in history
        ],
    }


def _coerce(f: Feature, values: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    fields = {x.name: x for x in f.fields}
    for name, value in values.items():
        spec = fields.get(name)
        if spec is None:
            continue
        if spec.type == "bool":
            out[name] = bool(value) if not isinstance(value, str) else value.lower() in ("1", "true", "yes", "да", "on")
        elif spec.type == "int":
            try:
                number = int(str(value).strip())
            except ValueError as exc:
                raise DomainError(f"«{spec.label}»: нужно целое число") from exc
            if spec.min is not None and number < spec.min or spec.max is not None and number > spec.max:
                raise DomainError(f"«{spec.label}»: допустимо от {spec.min} до {spec.max}")
            out[name] = number
        elif spec.type in ("text", "template"):
            text = str(value or "").strip()
            if spec.type == "template":
                problems = tpl.validate_template(text)
                if problems:
                    raise DomainError(f"«{spec.label}»: " + "; ".join(problems))
            if name in ("offline_from", "offline_to"):
                hh, _, mm = text.partition(":")
                if not (hh.isdigit() and mm.isdigit() and int(hh) < 24 and int(mm) < 60):
                    raise DomainError(f"«{spec.label}»: формат ЧЧ:ММ")
            out[name] = text[:2000]
        elif spec.type == "choice":
            allowed = {c[0] for c in spec.choices}
            if value not in allowed:
                raise DomainError(f"«{spec.label}»: недопустимое значение")
            out[name] = value
        elif spec.type == "multichoice":
            allowed = {c[0] for c in spec.choices}
            items = value if isinstance(value, list) else [v.strip() for v in str(value).split(",") if v.strip()]
            out[name] = [v for v in items if v in allowed]
        elif spec.type == "list":
            items = value if isinstance(value, list) else [v.strip() for v in str(value).replace("\n", ",").split(",") if v.strip()]
            out[name] = [str(v)[:120] for v in items][:200]
    return out


async def update(session: AsyncSession, code: str, values: dict[str, Any], actor: Actor) -> AutoSetting:
    f = feature(code)
    row = await get_row(session, code)
    clean = _coerce(f, values)
    if f.code == "auto_delivery":
        clean.pop("reserve", None)  # never configurable
    config = effective_config(f, row)
    config.update(clean)
    row.config = config
    row.updated_by = actor.label
    row.updated_at = utcnow()
    await audit(session, actor, "autosetting.update", entity_type="auto_setting", entity_id=code, details={"changed": sorted(clean)})
    await automation_log(session, code, "settings_saved", LogResult.OK, f"Изменено: {', '.join(sorted(clean)) or '—'} ({actor.label})")
    return row


async def set_enabled(session: AsyncSession, code: str, enabled: bool, actor: Actor) -> AutoSetting:
    f = feature(code)
    row = await get_row(session, code)
    state = integration_state(f)
    if enabled and state["state"] == "unavailable":
        raise DomainError(f"{f.label}: интеграция недоступна. {state['reason']}", code="integration_unavailable")
    row.enabled = enabled
    row.updated_by = actor.label
    row.updated_at = utcnow()
    await audit(session, actor, "autosetting.toggle", entity_type="auto_setting", entity_id=code, details={"enabled": enabled})
    await automation_log(
        session, code, "enabled" if enabled else "disabled", LogResult.OK, f"{'Включено' if enabled else 'Выключено'}: {actor.label}"
    )
    return row


async def reset(session: AsyncSession, code: str, actor: Actor) -> AutoSetting:
    f = feature(code)
    row = await get_row(session, code)
    row.config = copy.deepcopy(f.defaults)
    row.updated_by = actor.label
    row.updated_at = utcnow()
    await audit(session, actor, "autosetting.reset", entity_type="auto_setting", entity_id=code)
    await automation_log(session, code, "reset", LogResult.OK, f"Сброс к стандартным значениям ({actor.label})")
    return row


async def preview(session: AsyncSession, code: str, field_name: str | None = None, context: dict[str, Any] | None = None) -> str:
    f = feature(code)
    row = await get_row(session, code)
    cfg = effective_config(f, row)
    name = field_name or f.preview_field
    if not name or name not in cfg:
        return ""
    shop = (await app_settings.get_setting(session, "shop.profile"))["name"]
    return tpl.render(str(cfg[name]), {**tpl.SAMPLE, "shop": shop, **(context or {})})


async def test(session: AsyncSession, code: str, actor: Actor) -> dict[str, Any]:
    """Dry test: renders the text with sample data and validates the setting.
    Never sends anything to buyers."""
    f = feature(code)
    row = await get_row(session, code)
    cfg = effective_config(f, row)
    problems: list[str] = []
    for spec in f.fields:
        if spec.type == "template":
            problems += [f"{spec.label}: {p}" for p in tpl.validate_template(str(cfg.get(spec.name, "")))]
    texts = {}
    shop = (await app_settings.get_setting(session, "shop.profile"))["name"]
    for spec in f.fields:
        if spec.type == "template":
            texts[spec.label] = tpl.render(str(cfg.get(spec.name, "")), {**tpl.SAMPLE, "shop": shop})
    state = integration_state(f)
    result = LogResult.ERROR if problems else LogResult.OK
    await automation_log(session, code, "test", result, "; ".join(problems) or f"Тест пройден ({state['label']})")
    return {"ok": not problems, "problems": problems, "texts": texts, "integration": state}


async def emergency_disable_all(session: AsyncSession, actor: Actor, reason: str) -> int:
    rows = (await session.execute(select(AutoSetting).where(AutoSetting.enabled.is_(True)))).scalars().all()
    for row in rows:
        row.enabled = False
        row.updated_by = actor.label
    await app_settings.set_kill_switch(session, True, actor, reason)
    return len(rows)
