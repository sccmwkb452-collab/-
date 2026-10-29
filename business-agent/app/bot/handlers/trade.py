from decimal import Decimal
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    KeyboardButtonRequestUsers,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from sqlalchemy import select, update

from app.ai.state import normalize_currency, to_decimal
from app.bot.callbacks import Cb
from app.bot.handlers.common import show
from app.bot.inputs import ask, input_field
from app.bot.states import TradeAdd
from app.bot.ui import btn, kb
from app.core.audit import audit
from app.db.models import TradeBotConfig, utcnow
from app.trading.guard import ALLOW_UNLISTED_BOTS, TradeBlocked, require_trade_bot, verify_shared_bot
from app.trading.registry import ADAPTERS, official_username_for

router = Router(name="trade")
REQUEST_IDS = {1: "cryptopay", 2: "manual"}


async def _cfg(session, owner, cid) -> TradeBotConfig | None:
    cfg = await session.get(TradeBotConfig, cid)
    return cfg if cfg and cfg.owner_id == owner.id else None


def _wrap(key, prompt):
    def deco(fn):
        async def wrapper(session, owner, text, data, ctx, **_):
            cfg = await _cfg(session, owner, int(data["obj_id"]))
            if cfg is None:
                return False, "Бот не найден"
            ok, msg = await fn(cfg, text)
            if ok:
                ctx.trade_adapters.forget(cfg.id)
                await audit(session, "trade_bot_settings", owner_id=owner.id, actor="user", trade_bot=cfg.bot_username, field=key)
            return ok, msg
        input_field(key, prompt, "trade:view")(wrapper)
        return fn
    return deco


@_wrap("tb_currencies", "Разрешённые валюты через запятую, например <code>TON, USDT</code>:")
async def tb_currencies(cfg, text):
    codes = [normalize_currency(c) for c in text.split(",")]
    if not codes or None in codes:
        return False, "Не распознал валюту"
    unsupported = [c for c in codes if cfg.supported_currencies and c not in cfg.supported_currencies]
    if unsupported:
        return False, f"Бот не поддерживает: {', '.join(unsupported)}. Доступно: {', '.join(cfg.supported_currencies)}"
    cfg.currencies = sorted(set(codes))
    return True, "Валюты: " + ", ".join(cfg.currencies)


@_wrap("tb_fees", "Комиссии сервиса для расчёта итоговой суммы: <code>процент фикс</code>, например <code>3 0</code>:")
async def tb_fees(cfg, text):
    parts = text.replace(",", ".").split()
    vals = [to_decimal(p) for p in parts]
    if len(vals) != 2 or None in vals or vals[0] > 50:
        return False, "Нужно два неотрицательных числа (процент ≤ 50)"
    cfg.fee_percent, cfg.fee_fixed = vals
    return True, f"Комиссия: {vals[0]}% + {vals[1]}"


@_wrap("tb_methods", "Способы оплаты, которые вы принимаете через этого бота (через запятую), например <code>баланс CryptoBot</code>:")
async def tb_methods(cfg, text):
    cfg.payment_methods = [m.strip() for m in text.split(",") if m.strip()][:10]
    return True, "Способы оплаты сохранены"


def _card(cfg: TradeBotConfig) -> str:
    return (
        f"<b>@{escape(cfg.bot_username)}</b> {'⭐️ активный' if cfg.is_active else ''}\n"
        f"Тип интеграции: {ADAPTERS.get(cfg.adapter, cfg.adapter)}\n"
        f"Проверенный Telegram ID: <code>{cfg.bot_user_id}</code> ({cfg.verified_at:%Y-%m-%d %H:%M} UTC)\n"
        f"Статус: {cfg.status}{(' — ' + escape(cfg.last_error)) if cfg.last_error else ''}\n"
        f"Поддерживаемые операции: {', '.join(cfg.capabilities or []) or 'не проверено'}\n"
        f"Валюты бота: {', '.join(cfg.supported_currencies or []) or '—'}\n"
        f"Разрешённые вами валюты: {', '.join(cfg.currencies or []) or '⚠️ не заданы'}\n"
        f"Способы оплаты: {escape(', '.join(cfg.payment_methods or []) or '—')}\n"
        f"Комиссия (для расчёта): {Decimal(cfg.fee_percent).normalize()}% + {Decimal(cfg.fee_fixed).normalize()}"
    )


async def _list(cq, session, owner):
    bots = (await session.scalars(select(TradeBotConfig).where(TradeBotConfig.owner_id == owner.id))).all()
    active = next((b for b in bots if b.is_active), None)
    lines = [
        "<b>🛍 Торговый бот</b>",
        "Сделки создаются <b>только</b> через выбранного здесь бота. Запасных ботов нет; ссылки на других ботов от "
        "собеседников игнорируются. Идентичность проверяется по числовому Telegram ID.",
        "",
        f"Активный: {('@' + escape(active.bot_username)) if active else '❌ не выбран — сделки невозможны'}",
        f"Неуказанные боты разрешены: {'да' if ALLOW_UNLISTED_BOTS else 'нет (не настраивается)'}",
        "Подтверждение пользователя перед сделкой — настраивается в «🤝 Управление сделками → Лимиты».",
    ]
    rows = [[btn("➕ Добавить бота", "trade", "add")]]
    for b in bots:
        rows.append([btn(("⭐️ " if b.is_active else "") + "@" + b.bot_username, "trade", "view", b.id)])
    await show(cq, "\n".join(lines), kb(*rows))


@router.callback_query(Cb.filter(F.s == "trade"))
async def trade(cq: CallbackQuery, callback_data: Cb, state: FSMContext, session, owner, ctx):
    a, i = callback_data.a, callback_data.i
    if a == "show":
        return await _list(cq, session, owner)
    if a == "add":
        rows = [[btn(title, "trade", "add_type", rid)] for rid, key in REQUEST_IDS.items() for title in [ADAPTERS[key]]]
        return await show(cq, "Выберите тип интеграции. Затем выберите бота кнопкой — так Telegram передаст его "
                              "настоящий числовой ID (по имени бота не определяем).", kb(*rows, back="trade"))
    if a == "add_type":
        key = REQUEST_IDS.get(i)
        if key is None:
            return await cq.answer()
        if key == "cryptopay" and not ctx.settings.crypto_pay_api_token:
            return await cq.answer("Сначала задайте CRYPTO_PAY_API_TOKEN в .env (токен не вводится в чат).", show_alert=True)
        await state.set_state(TradeAdd.choose_bot)
        await state.update_data(adapter=key)
        official = official_username_for(key, ctx.settings)
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, keyboard=[[KeyboardButton(
            text="🤖 Выбрать бота",
            request_users=KeyboardButtonRequestUsers(request_id=i, user_is_bot=True, max_quantity=1, request_username=True),
        )], [KeyboardButton(text="Отмена")]])
        hint = f"Выберите официального бота <code>@{official}</code>." if official else "Выберите торгового бота."
        await cq.message.answer(hint, reply_markup=markup)
        return await cq.answer()

    cfg = await _cfg(session, owner, i)
    if cfg is None:
        return await cq.answer("Бот не найден", show_alert=True)
    if a in ("f_tb_currencies", "f_tb_fees", "f_tb_methods"):
        return await ask(cq, state, a[2:], obj_id=cfg.id)
    if a == "activate":
        await session.execute(update(TradeBotConfig).where(TradeBotConfig.owner_id == owner.id).values(is_active=False))
        cfg.is_active = True
        await audit(session, "trade_bot_activated", owner_id=owner.id, actor="user", trade_bot=cfg.bot_username,
                    bot_user_id=cfg.bot_user_id)
    elif a == "check":
        if not cfg.is_active:
            return await cq.answer("Проверяется только активный бот — сначала сделайте его активным.", show_alert=True)
        try:
            guarded = await require_trade_bot(session, owner.id, ctx.trade_adapters)
            cfg.capabilities = [str(c) for c in guarded.adapter.static_capabilities()]
            msg = "✅ Бот доступен"
        except TradeBlocked as exc:
            msg = "⚠️ " + exc.message
        await audit(session, "trade_bot_check", "ok" if msg.startswith("✅") else "error", owner_id=owner.id,
                    trade_bot=cfg.bot_username, error=None if msg.startswith("✅") else msg)
        await cq.answer(msg[:190], show_alert=True)
    elif a == "delete":
        ctx.trade_adapters.forget(cfg.id)
        await session.delete(cfg)
        await audit(session, "trade_bot_deleted", owner_id=owner.id, actor="user", trade_bot=cfg.bot_username)
        await session.flush()
        return await _list(cq, session, owner)
    await show(cq, _card(cfg), kb(
        [btn("⭐️ Сделать активным", "trade", "activate", cfg.id), btn("🩺 Проверить", "trade", "check", cfg.id)],
        [btn("💱 Валюты", "trade", "f_tb_currencies", cfg.id), btn("💳 Способы оплаты", "trade", "f_tb_methods", cfg.id)],
        [btn("🧾 Комиссии", "trade", "f_tb_fees", cfg.id), btn("🗑 Удалить", "trade", "delete", cfg.id)],
        back="trade",
    ))


@router.message(TradeAdd.choose_bot, F.text == "Отмена")
async def cancel_add(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())


@router.message(TradeAdd.choose_bot, F.users_shared)
async def bot_shared(message: Message, state: FSMContext, session, owner, ctx):
    data = await state.get_data()
    await state.clear()
    adapter_key = data.get("adapter")
    shared = message.users_shared.users[0] if message.users_shared.users else None
    if adapter_key is None or shared is None:
        await message.answer("Не удалось получить бота.", reply_markup=ReplyKeyboardRemove())
        return
    error = verify_shared_bot(adapter_key, shared.user_id, shared.username, official_username_for(adapter_key, ctx.settings))
    if error:
        await audit(session, "trade_bot_added", "blocked", owner_id=owner.id, actor="user", error=error)
        await message.answer(f"⛔️ {escape(error)}", reply_markup=ReplyKeyboardRemove())
        return
    existing = await session.scalar(select(TradeBotConfig).where(
        TradeBotConfig.owner_id == owner.id, TradeBotConfig.bot_user_id == shared.user_id))
    cfg = existing or TradeBotConfig(owner_id=owner.id, bot_user_id=shared.user_id, currencies=[], payment_methods=[],
                                     capabilities=[], supported_currencies=[])
    cfg.adapter, cfg.bot_username, cfg.verified_at = adapter_key, shared.username.lower(), utcnow()
    if existing is None:
        session.add(cfg)
    await session.flush()
    ctx.trade_adapters.forget(cfg.id)
    await audit(session, "trade_bot_added", owner_id=owner.id, actor="user", trade_bot=cfg.bot_username, bot_user_id=cfg.bot_user_id)
    await message.answer(f"✅ Бот @{escape(cfg.bot_username)} добавлен (ID {cfg.bot_user_id}).", reply_markup=ReplyKeyboardRemove())
    await message.answer(_card(cfg) + "\n\nСделайте его активным, проверьте и задайте валюты.", reply_markup=kb(
        [btn("⭐️ Сделать активным", "trade", "activate", cfg.id), btn("💱 Валюты", "trade", "f_tb_currencies", cfg.id)],
        back="trade"))
