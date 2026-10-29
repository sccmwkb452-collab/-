from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select, update

from app.ai.state import to_decimal
from app.bot.callbacks import Cb
from app.bot.handlers.common import show
from app.bot.inputs import ask, input_field
from app.bot.states import Input
from app.bot.ui import btn, contact_title, kb, onoff
from app.core.audit import audit
from app.db.models import OutreachStatus, OutreachTask, ParserConfig, SearchResult, utcnow
from app.parsers.base import ParserError
from app.parsers.file_import import parse_import_file
from app.parsers.pipeline import run_parser
from app.parsers.registry import ADAPTERS, build_adapter, detect_source

router = Router(name="parsers")
ROLE_RU = {"seller": "продавцы", "buyer": "покупатели", "any": "любые"}
MAX_IMPORT_BYTES = 5 * 1024 * 1024


async def _parser(session, owner, pid) -> ParserConfig | None:
    cfg = await session.get(ParserConfig, pid)
    return cfg if cfg and cfg.owner_id == owner.id else None


@input_field("parser_new", "Укажите источник парсера: URL API, ссылку t.me/nft/…, slug коллекции подарков "
             "или @username парсер-бота. Для импорта файла напишите <code>файл</code>.", "parsers")
async def parser_new(session, owner, text, **_):
    if text.lower() in ("файл", "file", "csv", "json"):
        adapter, explanation = "file_import", "Импорт CSV/JSON. Загрузите файл в карточке парсера."
    else:
        det = detect_source(text)
        if det.adapter is None:
            return False, escape(det.explanation)
        adapter, explanation = det.adapter, det.explanation
    n = await session.scalar(select(func.count(ParserConfig.id)).where(ParserConfig.owner_id == owner.id)) or 0
    cfg = ParserConfig(owner_id=owner.id, name=f"parser{n + 1}", adapter=adapter,
                       resource="" if adapter == "file_import" else text, keywords=[], filters={}, ranges={},
                       stop_rules={"max_results": 200})
    session.add(cfg)
    await session.flush()
    await audit(session, "parser_added", owner_id=owner.id, actor="user", parser=cfg.name, adapter=adapter)
    return True, f"Парсер <b>{cfg.name}</b> создан ({ADAPTERS[adapter].title}).\n{escape(explanation)}"


def _field(key: str, prompt: str):
    def deco(fn):
        async def wrapper(session, owner, text, data, **kw):
            cfg = await _parser(session, owner, int(data["obj_id"]))
            if cfg is None:
                return False, "Парсер не найден"
            return await fn(cfg, text, session=session, owner=owner)
        input_field(key, prompt, "parsers:view")(wrapper)
        return fn
    return deco


@_field("p_name", "Новое название парсера (латиница/цифры, используется в PARSER_TOKEN_<ИМЯ>):")
async def p_name(cfg, text, session, owner):
    clean = "".join(c for c in text if c.isalnum() or c in "_-")[:64]
    if not clean:
        return False, "Пустое название"
    if await session.scalar(select(ParserConfig.id).where(ParserConfig.owner_id == owner.id, ParserConfig.name == clean,
                                                          ParserConfig.id != cfg.id)):
        return False, "Такое название уже есть"
    cfg.name = clean
    return True, f"Название: {clean}"


@_field("p_keywords", "Ключевые слова через запятую (пусто — «-»):")
async def p_keywords(cfg, text, **_):
    cfg.keywords = [] if text == "-" else [k.strip() for k in text.split(",") if k.strip()][:50]
    return True, "Ключевые слова: " + escape(", ".join(cfg.keywords) or "—")


@_field("p_filters", "Фильтры в виде <code>поле=значение; поле=значение</code> (например <code>model=Pepe; backdrop=Black</code>), «-» чтобы очистить:")
async def p_filters(cfg, text, **_):
    if text == "-":
        cfg.filters = {}
        return True, "Фильтры очищены"
    pairs = [p.split("=", 1) for p in text.split(";") if "=" in p]
    if not pairs:
        return False, "Формат: поле=значение; поле=значение"
    cfg.filters = {k.strip(): v.strip() for k, v in pairs}
    return True, "Фильтры: " + escape(str(cfg.filters))


@_field("p_geo", "География (город/страна, «-» — без ограничения):")
async def p_geo(cfg, text, **_):
    cfg.geo = None if text == "-" else text[:128]
    return True, "География: " + escape(cfg.geo or "—")


@_field("p_ranges", "Диапазоны: <code>поле=мин..макс; …</code>, например <code>price=1..50; model_rarity_percent=..1.5; number=1..300</code>. «-» — очистить:")
async def p_ranges(cfg, text, **_):
    if text == "-":
        cfg.ranges = {}
        return True, "Диапазоны очищены"
    ranges = {}
    for part in text.split(";"):
        if "=" not in part or ".." not in part:
            continue
        key, bounds = part.split("=", 1)
        lo, hi = bounds.split("..", 1)
        if (lo.strip() and to_decimal(lo) is None) or (hi.strip() and to_decimal(hi) is None):
            return False, f"Не число в «{escape(part)}»"
        ranges[key.strip()] = {"min": lo.strip() or None, "max": hi.strip() or None}
    if not ranges:
        return False, "Формат: поле=мин..макс"
    cfg.ranges = ranges
    return True, "Диапазоны: " + escape(str(ranges))


@_field("p_limits", "Лимиты обращений: <code>в_день всего</code>, например <code>10 100</code>:")
async def p_limits(cfg, text, **_):
    parts = text.split()
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return False, "Нужно два числа"
    cfg.daily_contact_limit, cfg.total_contact_limit = min(int(parts[0]), 200), int(parts[1])
    return True, f"Лимиты: {cfg.daily_contact_limit}/день, {cfg.total_contact_limit} всего"


@_field("p_stop", "Правила остановки: <code>просмотреть найти интервал_часов</code>, например <code>200 20 24</code> "
        "(интервал 0 — только ручной запуск):")
async def p_stop(cfg, text, **_):
    parts = text.split()
    if len(parts) != 3 or not all(p.replace(".", "", 1).isdigit() for p in parts):
        return False, "Нужно три числа"
    cfg.stop_rules = {"max_results": min(int(float(parts[0])), 5000), "stop_after_matches": int(float(parts[1])),
                      "interval_hours": float(parts[2]) or None}
    return True, "Правила остановки сохранены"


@_field("p_resource", "Новый источник (username, ссылка или URL API):")
async def p_resource(cfg, text, **_):
    cfg.resource = text[:1000]
    return True, "Источник сохранён"


def _card(cfg: ParserConfig, found: int, queued: int) -> tuple[str, object]:
    sr = cfg.stop_rules or {}
    text = (
        f"<b>🔎 {escape(cfg.name)}</b> — {ADAPTERS[cfg.adapter].title}\n"
        f"Источник: {escape(cfg.resource or ('файл: ' + str(len(cfg.import_rows or [])) + ' строк'))}\n"
        f"Ищем: {ROLE_RU.get(cfg.target_role, cfg.target_role)}\n"
        f"Ключевые слова: {escape(', '.join(cfg.keywords or []) or '—')}\n"
        f"Фильтры: {escape(str(cfg.filters or '—'))}\n"
        f"География: {escape(cfg.geo or '—')}\n"
        f"Диапазоны: {escape(str(cfg.ranges or '—'))}\n"
        f"Лимиты обращений: {cfg.daily_contact_limit}/день, {cfg.total_contact_limit} всего\n"
        f"Остановка: просмотреть {sr.get('max_results', 200)}, найти {sr.get('stop_after_matches', '∞')}, "
        f"по расписанию: {('каждые ' + str(sr['interval_hours']) + ' ч') if sr.get('interval_hours') else 'нет'}\n"
        f"Статус: {onoff(cfg.enabled)} · {escape(cfg.status)}"
        + (f"\nОшибка: {escape(cfg.last_error)}" if cfg.last_error else "")
        + f"\nНайдено всего: {found}, в очереди обращений: {queued}"
    )
    rows = [
        [btn("▶️ Запустить", "parsers", "run", cfg.id), btn("✅ Проверить", "parsers", "validate", cfg.id)],
        [btn("🏷 Название", "parsers", "f_p_name", cfg.id), btn("👥 Роль", "parsers", "role", cfg.id)],
        [btn("🔑 Ключевые слова", "parsers", "f_p_keywords", cfg.id), btn("🎛 Фильтры", "parsers", "f_p_filters", cfg.id)],
        [btn("🌍 География", "parsers", "f_p_geo", cfg.id), btn("📏 Диапазоны", "parsers", "f_p_ranges", cfg.id)],
        [btn("🚦 Лимиты", "parsers", "f_p_limits", cfg.id), btn("🛑 Остановка", "parsers", "f_p_stop", cfg.id)],
    ]
    if cfg.adapter == "file_import":
        rows.append([btn("📤 Загрузить файл", "parsers", "upload", cfg.id)])
    else:
        rows.append([btn("🔗 Источник", "parsers", "f_p_resource", cfg.id)])
    rows.append([btn("⏯ Вкл/выкл", "parsers", "toggle", cfg.id), btn("🗑 Удалить", "parsers", "delete", cfg.id)])
    return text, kb(*rows, back="parsers")


async def _show_card(cq, session, cfg):
    found = await session.scalar(select(func.count(SearchResult.id)).where(SearchResult.parser_id == cfg.id)) or 0
    queued = await session.scalar(select(func.count(OutreachTask.id)).where(
        OutreachTask.parser_id == cfg.id, OutreachTask.status.in_([OutreachStatus.PENDING_APPROVAL, OutreachStatus.APPROVED]))) or 0
    await show(cq, *_card(cfg, found, queued))


async def _queue(cq, session, owner):
    tasks = (await session.scalars(select(OutreachTask).where(
        OutreachTask.owner_id == owner.id, OutreachTask.status == OutreachStatus.PENDING_APPROVAL)
        .order_by(OutreachTask.id).limit(10))).all()
    lines = ["<b>📬 Очередь обращений (ждут одобрения)</b>",
             f"Лимит: {owner.outreach_daily_limit}/день, пауза между обращениями {owner.outreach_min_interval_seconds} с."]
    rows = []
    for t in tasks:
        profile = t.contact.profile or {}
        lines.append(f"• #{t.id} {contact_title(t.contact)} — {escape(str(profile.get('attributes') or profile.get('text') or '')[:120])}")
        rows.append([btn(f"✅ #{t.id}", "parsers", "out_ok", t.id), btn(f"✖️ #{t.id}", "parsers", "out_cancel", t.id)])
    if tasks:
        rows.insert(0, [btn("✅ Одобрить все", "parsers", "out_ok_all")])
    else:
        lines.append("Очередь пуста.")
    await show(cq, "\n".join(lines), kb(*rows, back="parsers"))


@router.callback_query(Cb.filter(F.s == "parsers"))
async def parsers(cq: CallbackQuery, callback_data: Cb, state: FSMContext, session, owner, ctx):
    a, i = callback_data.a, callback_data.i
    if a == "add":
        return await ask(cq, state, "parser_new")
    if a == "queue":
        return await _queue(cq, session, owner)
    if a in ("out_ok", "out_cancel", "out_done"):
        task = await session.get(OutreachTask, i)
        if task is None or task.owner_id != owner.id:
            return await cq.answer("Задача не найдена", show_alert=True)
        if a == "out_ok" and task.status == OutreachStatus.PENDING_APPROVAL and not task.contact.opted_out:
            task.status = OutreachStatus.APPROVED
        elif a == "out_cancel" and task.status != OutreachStatus.SENT:
            task.status = OutreachStatus.CANCELLED
        elif a == "out_done" and task.status == OutreachStatus.MANUAL_REQUIRED:
            task.status, task.sent_at = OutreachStatus.SENT, utcnow()
            task.contact.first_contacted_at = task.contact.first_contacted_at or utcnow()
            task.contact.last_contacted_at = utcnow()
            task.contact.contact_attempts += 1
            await audit(session, "outreach", "ok", owner_id=owner.id, actor="user", contact_id=task.contact_id, manual=True)
            return await cq.answer("Отмечено. Агент продолжит, когда собеседник ответит.", show_alert=True)
        if a in ("out_done", "out_cancel") and cq.message.text and "вручную" in cq.message.text:
            return await cq.answer("Готово")
        return await _queue(cq, session, owner)
    if a == "out_ok_all":
        await session.execute(update(OutreachTask).where(
            OutreachTask.owner_id == owner.id, OutreachTask.status == OutreachStatus.PENDING_APPROVAL
        ).values(status=OutreachStatus.APPROVED))
        await audit(session, "outreach_approved_all", owner_id=owner.id, actor="user")
        return await _queue(cq, session, owner)

    if a == "show":
        cfgs = (await session.scalars(select(ParserConfig).where(ParserConfig.owner_id == owner.id))).all()
        pending = await session.scalar(select(func.count(OutreachTask.id)).where(
            OutreachTask.owner_id == owner.id, OutreachTask.status == OutreachStatus.PENDING_APPROVAL)) or 0
        lines = ["<b>🔎 Парсеры</b>"]
        if not cfgs:
            lines.append("Парсер не выбран — <b>режим без парсера</b>: агент работает только с входящими сообщениями "
                         "и уже существующими диалогами. Источники сам не придумывает.")
        rows = [[btn("➕ Добавить парсер", "parsers", "add")], [btn(f"📬 Очередь обращений ({pending})", "parsers", "queue")]]
        for c in cfgs:
            lines.append(f"• {escape(c.name)} — {ADAPTERS[c.adapter].title} {onoff(c.enabled)}")
            rows.append([btn(c.name, "parsers", "view", c.id)])
        return await show(cq, "\n".join(lines), kb(*rows))

    cfg = await _parser(session, owner, i)
    if cfg is None:
        return await cq.answer("Парсер не найден", show_alert=True)
    if a.startswith("f_"):
        key = a[2:]
        current = {"p_name": cfg.name, "p_keywords": ", ".join(cfg.keywords or []), "p_filters": str(cfg.filters or ""),
                   "p_geo": cfg.geo, "p_ranges": str(cfg.ranges or ""), "p_resource": cfg.resource,
                   "p_limits": f"{cfg.daily_contact_limit} {cfg.total_contact_limit}", "p_stop": str(cfg.stop_rules)}.get(key)
        return await ask(cq, state, key, escape(current or ""), obj_id=cfg.id)
    if a == "role":
        order = ["seller", "buyer", "any"]
        cfg.target_role = order[(order.index(cfg.target_role) + 1) % 3] if cfg.target_role in order else "seller"
    elif a == "toggle":
        cfg.enabled = not cfg.enabled
    elif a == "delete":
        await session.delete(cfg)
        await audit(session, "parser_deleted", owner_id=owner.id, actor="user", parser=cfg.name)
        await session.flush()
        return await show(cq, "Парсер удалён.", kb(back="parsers"))
    elif a == "upload":
        await state.set_state(Input.file)
        await state.update_data(obj_id=cfg.id)
        await cq.message.answer("Отправьте файл .csv или .json (до 5 МБ). Колонки: user_id, username, name, role, text, "
                                "price, currency, geo, url — остальные станут атрибутами.\n/cancel — отмена")
        return await cq.answer()
    elif a == "validate":
        adapter = build_adapter(cfg)
        try:
            await adapter.connect()
            ok, msg = await adapter.validate()
        except ParserError as exc:
            ok, msg = False, str(exc)
        finally:
            await adapter.disconnect()
        cfg.status, cfg.last_error = ("ok", None) if ok else ("error", msg)
        await cq.answer(("✅ " if ok else "⚠️ ") + msg[:180], show_alert=True)
    elif a == "run":
        if owner.paused:
            return await cq.answer("Работа приостановлена", show_alert=True)
        await cq.answer("Запускаю…")
        report = await run_parser(session, owner, cfg, build_adapter(cfg))
        await session.flush()
        await cq.message.answer(f"🔎 <b>{escape(cfg.name)}</b>\n" + escape(report.render())
                                + ("\n\nКонтакты ждут одобрения в «📬 Очередь обращений»." if report.queued and owner.outreach_requires_approval else ""),
                                reply_markup=kb([btn("📬 Очередь", "parsers", "queue")], back="parsers"))
        return
    await _show_card(cq, session, cfg)


@router.message(Input.file, F.text == "/cancel")
async def cancel_file(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=kb(back="parsers"))


@router.message(Input.file, F.document)
async def receive_file(message: Message, state: FSMContext, session, owner):
    data = await state.get_data()
    cfg = await _parser(session, owner, int(data.get("obj_id", 0)))
    if cfg is None:
        await state.clear()
        return
    doc = message.document
    if doc.file_size and doc.file_size > MAX_IMPORT_BYTES:
        await message.answer("Файл больше 5 МБ.")
        return
    raw = (await message.bot.download(doc.file_id)).getvalue()
    try:
        rows = parse_import_file(raw, doc.file_name or "data.csv")
    except (ParserError, ValueError, UnicodeDecodeError) as exc:
        await message.answer(f"⚠️ Не удалось прочитать файл: {escape(str(exc))}")
        return
    cfg.import_rows = rows
    cfg.status = "ok"
    await state.clear()
    await audit(session, "parser_import", owner_id=owner.id, actor="user", parser=cfg.name, rows=len(rows))
    await message.answer(f"📥 Загружено строк: {len(rows)}. Запустите парсер, чтобы отфильтровать контакты.",
                         reply_markup=kb([btn("▶️ Запустить", "parsers", "run", cfg.id)], back="parsers"))
