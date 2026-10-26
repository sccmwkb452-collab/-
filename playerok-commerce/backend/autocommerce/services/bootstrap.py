"""Initial data: roles, product categories with compliance status, the
researched suppliers (docs/RESEARCH.md), the global price rule, default
auto-settings, autoresponder rules and demo image templates.

Idempotent: running it again adds what is missing and never overwrites what
the owner changed (except the verification facts of suppliers, which are
research data, not settings).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import ComplianceStatus, PurchaseMode, SupplierStatus
from ..database.models import AutoresponderRule, PriceRule, ProductCategory, Supplier
from . import autosettings
from .auth import ensure_roles
from .pricing import PricingPolicy

CHECKED = "2026-10-25"
COMMISSION_SOURCE = (
    "vc.ru (вторичный источник, официально не подтверждено): 10 % — донаты, пополнения, лицензии, подписки; 20 % — остальное"
)

# code, name, group, commission %, compliance, note, dispute risk %, auto delivery possible, listing template
CATEGORIES: list[tuple[str, str, str, str, ComplianceStatus, str, str, bool, str]] = [
    (
        "tg_stars",
        "Telegram Stars",
        "telegram",
        "10",
        ComplianceStatus.APPROVED,
        "Fragment официально позволяет покупать Stars для других пользователей (страница /stars/buy). Закупка — вручную через TON Connect.",
        "3",
        False,
        "telegram_stars",
    ),
    (
        "tg_premium",
        "Telegram Premium",
        "telegram",
        "10",
        ComplianceStatus.APPROVED,
        "Fragment официально позволяет дарить Premium другим пользователям (страница /premium/gift). Закупка — вручную.",
        "3",
        False,
        "telegram_premium",
    ),
    (
        "tg_gifts",
        "Подарки Telegram",
        "telegram",
        "20",
        ComplianceStatus.NEEDS_REVIEW,
        "Перепродажа подарков требует проверки правил Telegram и Fragment.",
        "8",
        False,
        "default",
    ),
    (
        "promo_telegram",
        "Продвижение в Telegram",
        "promotion",
        "20",
        ComplianceStatus.NEEDS_REVIEW,
        "Накрутка подписчиков и просмотров может нарушать правила Telegram. Одобрите категорию, только если услуги допустимы.",
        "10",
        False,
        "promotion",
    ),
    (
        "promo_social",
        "Продвижение в соцсетях",
        "promotion",
        "20",
        ComplianceStatus.NEEDS_REVIEW,
        "Большинство соцсетей запрещают накрутку. Одобряйте отдельные услуги после проверки правил платформы.",
        "12",
        False,
        "promotion",
    ),
    (
        "steam_cards",
        "Steam Gift Cards и Wallet Codes",
        "steam",
        "10",
        ComplianceStatus.APPROVED,
        "Официальные подарочные карты от авторизованного дистрибьютора. Указывайте регион: карта активируется только в своей валюте/регионе.",
        "5",
        True,
        "giftcard",
    ),
    (
        "steam_topup",
        "Пополнение Steam Wallet",
        "steam",
        "10",
        ComplianceStatus.NEEDS_REVIEW,
        "Средства кошелька Steam непередаваемы (SSA §3.C). Допустима продажа официальных кодов пополнения; прямое пополнение — проверьте способ.",
        "6",
        False,
        "default",
    ),
    (
        "steam_keys",
        "Ключи игр и DLC Steam",
        "steam",
        "10",
        ComplianceStatus.NEEDS_REVIEW,
        "Только ключи от авторизованных дистрибьюторов. Поставщик с API пока не подключён.",
        "8",
        True,
        "giftcard",
    ),
    (
        "steam_items",
        "Игровые предметы Steam",
        "steam",
        "20",
        ComplianceStatus.NEEDS_REVIEW,
        "Проверьте правила Steam и конкретной игры для продажи предметов за деньги вне Steam.",
        "10",
        False,
        "default",
    ),
    (
        "steam_rent",
        "Аренда аккаунтов Steam",
        "steam",
        "20",
        ComplianceStatus.BLOCKED,
        "Steam Subscriber Agreement §1.C запрещает передавать аккаунт и брать плату за его использование.",
        "20",
        False,
        "default",
    ),
    (
        "gc_apple",
        "Apple Gift Card",
        "giftcards",
        "10",
        ComplianceStatus.APPROVED,
        "Официальные карты от авторизованного дистрибьютора; регион карты должен совпадать с регионом Apple ID.",
        "6",
        True,
        "giftcard",
    ),
    (
        "gc_playstation",
        "PlayStation Store",
        "giftcards",
        "10",
        ComplianceStatus.APPROVED,
        "Официальные карты; регион аккаунта PSN должен совпадать с регионом карты.",
        "6",
        True,
        "giftcard",
    ),
    (
        "gc_xbox",
        "Xbox Gift Card",
        "giftcards",
        "10",
        ComplianceStatus.APPROVED,
        "Официальные карты; учитывайте регион.",
        "6",
        True,
        "giftcard",
    ),
    (
        "gc_nintendo",
        "Nintendo eShop",
        "giftcards",
        "10",
        ComplianceStatus.APPROVED,
        "Официальные карты; учитывайте регион.",
        "6",
        True,
        "giftcard",
    ),
    (
        "gc_roblox",
        "Roblox Gift Card (Robux)",
        "roblox",
        "10",
        ComplianceStatus.APPROVED,
        "Только официальные подарочные карты Roblox.",
        "6",
        True,
        "giftcard",
    ),
    (
        "roblox_items",
        "Предметы Roblox (Adopt Me и др.)",
        "roblox",
        "20",
        ComplianceStatus.BLOCKED,
        "По вторичным источникам правила Roblox запрещают продавать предметы за реальные деньги вне платформы. Официальный текст не проверен.",
        "20",
        False,
        "default",
    ),
    (
        "game_pubg",
        "PUBG Mobile UC",
        "games",
        "10",
        ComplianceStatus.APPROVED,
        "Только официальные ваучеры от авторизованных дистрибьюторов.",
        "6",
        True,
        "giftcard",
    ),
    (
        "game_vouchers",
        "Ваучеры игр (Battle.net, Riot, Fortnite, Minecraft, EA FC)",
        "games",
        "10",
        ComplianceStatus.NEEDS_REVIEW,
        "Только официальные ваучеры; наличие проверяется по каталогу поставщика.",
        "6",
        True,
        "giftcard",
    ),
    (
        "sub_ai",
        "Подписки ИИ (Claude, ChatGPT и др.)",
        "subscriptions",
        "10",
        ComplianceStatus.NO_LEGAL_SOURCE,
        "Подтверждённой реселлерской программы не найдено; передача личных аккаунтов запрещена правилами сервисов.",
        "15",
        False,
        "default",
    ),
    (
        "sub_software",
        "Лицензии ПО и облачных сервисов",
        "subscriptions",
        "10",
        ComplianceStatus.NEEDS_REVIEW,
        "Только лицензионные ключи от реселлеров с правом перепродажи.",
        "8",
        True,
        "giftcard",
    ),
    (
        "sub_vpn",
        "VPN и другие подписки",
        "subscriptions",
        "10",
        ComplianceStatus.NEEDS_REVIEW,
        "Только официальные подарочные коды сервисов.",
        "8",
        True,
        "giftcard",
    ),
]

SUPPLIERS: list[dict[str, Any]] = [
    {
        "code": "fragment",
        "name": "Fragment",
        "website": "https://fragment.com/",
        "adapter": "fragment",
        "categories": ["tg_stars", "tg_premium"],
        "integration_method": "Публичные страницы цен /stars/buy и /premium/gift; покупка — TON Connect в браузере",
        "status": SupplierStatus.MONITOR_ONLY,
        "status_reason": "Публичного API покупки нет: цены читаются автоматически, закупка — вручную",
        "purchase_mode": PurchaseMode.MANUAL,
        "currency": "USD",
        "refund_policy": "Транзакции в блокчейне TON необратимы (fragment.com/terms).",
        "policy_note": "Покупка для другого пользователя предусмотрена площадкой.",
        "verification": {
            "checked_at": CHECKED,
            "sources": ["https://fragment.com/stars/buy", "https://fragment.com/premium/gift", "https://fragment.com/terms"],
            "facts": [
                "Пакеты Stars от 50 до 10 000 000 с ценой в USD и TON — подтверждено",
                "Premium 3/6/12 месяцев в подарок — подтверждено",
                "Оплата криптовалютой через TON Connect, вход через Telegram — подтверждено",
            ],
        },
    },
    {
        "code": "vexboost",
        "name": "VexBoost",
        "website": "https://vexboost.ru/",
        "adapter": "smm_v2",
        "categories": ["promo_telegram", "promo_social"],
        "integration_method": "SMM API v2: https://vexboost.ru/api/v2 (ключ из личного кабинета)",
        "status": SupplierStatus.NOT_CONFIGURED,
        "status_reason": "Нужен API-ключ VexBoost",
        "purchase_mode": PurchaseMode.MONITOR,
        "currency": "RUB",
        "refund_policy": "Возврат только при невозможности выполнить заказ, удержание 10 %, до 7 рабочих дней (vexboost.ru/politika-vozvrata).",
        "policy_note": "Каждая услуга требует проверки правил платформы-получателя (накрутка часто запрещена).",
        "verification": {
            "checked_at": CHECKED,
            "sources": [
                "https://vexboost.ru/oferta",
                "https://vexboost.ru/kontakty-skidka-reselleram",
                "https://vexboost.ru/politika-vozvrata",
            ],
            "facts": [
                "Исполнитель: ИП Кулешов Даниил Евгеньевич — подтверждено (оферта)",
                "Endpoint /api/v2 отвечает в формате SMM API v2 — подтверждено без ключа",
                "Реселлинг приветствуется (страница «Скидка реселлерам») — подтверждено",
                "Полный контракт API — проверить с ключом",
            ],
        },
    },
    {
        "code": "reloadly",
        "name": "Reloadly",
        "website": "https://www.reloadly.com/",
        "adapter": "reloadly",
        "categories": ["steam_cards", "gc_apple", "gc_playstation", "gc_xbox", "gc_nintendo", "gc_roblox", "game_pubg", "game_vouchers"],
        "integration_method": "Gift Cards API (OAuth client credentials), есть песочница",
        "status": SupplierStatus.NOT_CONFIGURED,
        "status_reason": "Нужны client_id и client_secret (сначала песочница)",
        "purchase_mode": PurchaseMode.MONITOR,
        "currency": "USD",
        "refund_policy": "Заказ подарочной карты невозвратный.",
        "policy_note": "Наличие брендов и стран определяется каталогом после подключения.",
        "verification": {
            "checked_at": CHECKED,
            "sources": ["https://giftcards-sandbox.reloadly.com", "https://www.reloadly.com/blog/wp-json/wp/v2/posts/2787"],
            "facts": [
                "Sandbox API существует (401 MISSING_TOKEN без токена) — подтверждено",
                "Ассортимент — не подтверждён до подключения",
            ],
        },
    },
    {
        "code": "kosell",
        "name": "KOSell",
        "website": "https://kosell.store/",
        "adapter": "none",
        "categories": ["steam_rent"],
        "integration_method": "Public API v1.1.0 (X-API-Key) — аренда аккаунтов Steam",
        "status": SupplierStatus.BLOCKED_BY_POLICY,
        "status_reason": "Аренда аккаунтов нарушает Steam Subscriber Agreement §1.C — интеграция не создана",
        "purchase_mode": PurchaseMode.MONITOR,
        "currency": "USD",
        "policy_note": "«You may not … sell or charge others for the right to use your Account» — SSA §1.C.",
        "verification": {
            "checked_at": CHECKED,
            "sources": ["https://kosell.store/api/openapi.json", "https://store.steampowered.com/subscriber_agreement/"],
            "facts": ["API существует (OpenAPI 3.1, v1.1.0) — подтверждено", "Перепродажа аренды запрещена правилами Steam — подтверждено"],
        },
    },
    {
        "code": "manual",
        "name": "Ручные закупки",
        "website": "",
        "adapter": "manual",
        "categories": [],
        "integration_method": "Цены и закупки вносятся оператором",
        "status": SupplierStatus.CONNECTED,
        "status_reason": "API не требуется",
        "purchase_mode": PurchaseMode.MANUAL,
        "currency": "RUB",
        "verification": {"checked_at": CHECKED, "sources": [], "facts": []},
    },
]

DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "name": "Жалоба или проблема → оператору",
        "priority": 10,
        "match_type": "keywords",
        "patterns": [
            "обман",
            "мошен",
            "не работает",
            "не пришл",
            "не приш",
            "возврат",
            "жалоб",
            "спор",
            "не активир",
            "развод",
            "арбитраж",
        ],
        "action": "escalate",
        "reply_template": "Здравствуйте, {buyer}! Передал ваш вопрос по заказу {order_number} — разберёмся и ответим в ближайшее время.",
    },
    {
        "name": "Статус заказа",
        "priority": 20,
        "match_type": "keywords",
        "patterns": ["где мой", "где заказ", "статус", "что с заказом", "когда будет"],
        "action": "status",
        "reply_template": "Здравствуйте, {buyer}! Статус заказа {order_number}: {status}. {next_steps}",
    },
    {
        "name": "Сроки выдачи",
        "priority": 30,
        "match_type": "keywords",
        "patterns": ["сколько ждать", "срок", "как долго", "когда", "быстро"],
        "action": "reply",
        "reply_template": "Здравствуйте! Обычно выдача «{product}» занимает {delivery_time}. Текущий статус вашего заказа: {status}.",
    },
    {
        "name": "Наличие товара",
        "priority": 40,
        "match_type": "keywords",
        "patterns": ["в наличии", "есть ли", "наличие", "остались", "есть в наличии"],
        "action": "reply",
        "reply_template": "Здравствуйте! «{product}»: {availability}. Срок выдачи — {delivery_time}.",
    },
]


async def seed(session: AsyncSession) -> dict[str, int]:
    counts = {"roles": 0, "categories": 0, "suppliers": 0, "rules": 0}
    counts["roles"] = len(await ensure_roles(session))

    existing_cats = {c.code for c in (await session.execute(select(ProductCategory))).scalars()}
    for sort, (code, name, group, commission, compliance, note, risk, auto, template) in enumerate(CATEGORIES):
        if code in existing_cats:
            continue
        session.add(
            ProductCategory(
                code=code,
                name=name,
                group=group,
                marketplace_commission_pct=Decimal(commission),
                commission_source=COMMISSION_SOURCE,
                compliance_status=compliance,
                compliance_note=note,
                dispute_risk_pct=Decimal(risk),
                auto_delivery_possible=auto,
                listing_template=template,
                sort=sort * 10,
            )
        )
        counts["categories"] += 1

    suppliers = {s.code: s for s in (await session.execute(select(Supplier))).scalars()}
    for data in SUPPLIERS:
        supplier = suppliers.get(data["code"])
        if supplier is None:
            session.add(Supplier(**data))
            counts["suppliers"] += 1
        else:
            supplier.verification = data["verification"]
            supplier.website = data["website"]
            supplier.integration_method = data["integration_method"]
            if data["status"] is SupplierStatus.BLOCKED_BY_POLICY:
                supplier.status = SupplierStatus.BLOCKED_BY_POLICY
                supplier.status_reason = data["status_reason"]

    if (await session.execute(select(PriceRule).where(PriceRule.scope == "global"))).scalar_one_or_none() is None:
        session.add(PriceRule(scope="global", values=PricingPolicy().to_values()))

    if (await session.execute(select(AutoresponderRule.id).limit(1))).scalar_one_or_none() is None:
        for rule in DEFAULT_RULES:
            session.add(AutoresponderRule(**rule))
            counts["rules"] += 1

    await autosettings.ensure_rows(session)
    from ..imaging import templates as image_templates

    await image_templates.sync_registry(session)
    await session.flush()
    return counts
