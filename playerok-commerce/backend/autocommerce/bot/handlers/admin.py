"""🛡 Безопасность, 🔔 Уведомления, 🧾 Журнал операций, ⚙️ Настройки."""

from __future__ import annotations

from decimal import Decimal

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...database.enums import COMPLIANCE_LABELS, ComplianceStatus, JobStatus, NotificationStatus, Severity, SupplierOrderStatus, SyncStatus
from ...database.models import AuditLog, AutomationJob, AutomationLog, Notification, SupplierOrder, SyncRun, User
from ...integrations.marketplace.base import CAPABILITY_LABELS
from ...integrations.marketplace.playerok_manual import get_marketplace
from ...services import app_settings, catalog, notifications
from ...services.audit import Actor
from ...shared.errors import DomainError
from ...shared.timeutil import fmt_dt
from ..core import ask, make_router, on_input, require, show
from ..ui import SEP, b, confirm, empty, esc, kb, nav, onoff, pager, short

router = make_router("admin")


# --- 🛡 Безопасность ----------------------------------------------------------------


@router.callback_query(F.data == "sec:home")
async def security(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    ks = await app_settings.kill_switch(session)
    live = await app_settings.is_live(session)
    settings = get_settings()
    failed = (
        (await session.execute(select(AuditLog).where(AuditLog.action == "auth.login_failed").order_by(AuditLog.id.desc()).limit(5)))
        .scalars()
        .all()
    )
    actions = (
        (
            await session.execute(
                select(AuditLog).where(AuditLog.actor_type.in_(["web", "telegram", "cli"])).order_by(AuditLog.id.desc()).limit(6)
            )
        )
        .scalars()
        .all()
    )
    users = (await session.execute(select(func.count()).where(User.is_active.is_(True)))).scalar_one()
    linked = (await session.execute(select(func.count()).where(User.telegram_id.is_not(None)))).scalar_one()
    lines = [
        "🛡 <b>Безопасность</b>",
        SEP,
        f"Аварийная остановка: <b>{'🛑 включена' if ks.get('active') else '🟢 выключена'}</b>",
        f"Режим операций: <b>{'🟢 боевой' if live else '🧪 тестовый'}</b>"
        + ("" if settings.allow_live_operations else " (боевой запрещён на сервере)"),
        f"Пользователей панели: {users} · с привязанным Telegram: {linked}",
        f"Доступ к боту: владельцы из OWNER_TELEGRAM_IDS ({len(settings.owner_telegram_ids)}) и привязанные пользователи",
        f"Веб-панель: {esc(settings.web_base_url)}",
        "",
        "<b>Неудачные входы</b>",
    ]
    lines += [f"• {fmt_dt(a.created_at)} · {esc(a.actor_name or '?')} · {esc(a.ip or '')}" for a in failed] or [empty("нет")]
    lines.append("\n<b>Последние действия</b>")
    lines += [f"• {fmt_dt(a.created_at)} · {esc(a.actor_name)} · {esc(a.action)}" for a in actions] or [empty("нет")]
    lines.append("\n🔒 Секреты и ключи не показываются и не принимаются в Telegram.")
    kill = (
        b("▶️ Снять остановку", "sec:kill:off", style="success")
        if ks.get("active")
        else b("🛑 Аварийная остановка", "sec:kill:on", style="danger")
    )
    mode = b("🧪 Перейти в тестовый", "sec:mode:test") if live else b("🟢 Включить боевой режим", "sec:mode:live")
    await show(cb, "\n".join(lines), kb([kill], [mode], [b("🧾 Журнал", "log:audit:1")], nav()))


@router.callback_query(F.data.regexp(r"^sec:kill:(on|off)(:y)?$"))
async def kill_switch(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "security.manage")
    parts = cb.data.split(":")
    on = parts[2] == "on"
    if len(parts) == 3:
        text = (
            "Остановить ВСЮ автоматизацию? Новые заказы будут ждать оператора."
            if on
            else "Снять аварийную остановку? Включённые автонастройки снова начнут работать."
        )
        t, markup = confirm(text, f"sec:kill:{parts[2]}:y", "sec:home", danger=on)
        await show(cb, t, markup)
        return
    await app_settings.set_kill_switch(session, on, actor, "Telegram" if on else "")
    await notifications.notify(
        session,
        "system",
        "Аварийная остановка " + ("включена" if on else "снята"),
        f"Кем: {esc(actor.label)}",
        severity=Severity.CRITICAL if on else Severity.INFO,
    )
    await security(cb, session, actor)


@router.callback_query(F.data.regexp(r"^sec:mode:(test|live)(:y)?$"))
async def mode(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "settings.manage")
    parts = cb.data.split(":")
    target = parts[2]
    if target == "live" and "*" not in actor.permissions:
        raise DomainError("Боевой режим включает только владелец")
    if len(parts) == 3:
        text = (
            "Включить боевой режим? Закупки у подключённых поставщиков будут выполняться по-настоящему (в пределах режимов и лимитов)."
            if target == "live"
            else "Перейти в тестовый режим? Закупки будут только моделироваться."
        )
        t, markup = confirm(text, f"sec:mode:{target}:y", "sec:home", danger=target == "live")
        await show(cb, t, markup)
        return
    await app_settings.set_setting(session, "operations.mode", target, actor)
    await security(cb, session, actor)


# --- 🔔 Уведомления -------------------------------------------------------------------


@router.callback_query(F.data == "ntf:home")
async def notifications_home(cb: CallbackQuery, session: AsyncSession) -> None:
    prefs = await app_settings.get_setting(session, "notifications")
    qh = prefs["quiet_hours"]
    failed = (await session.execute(select(func.count()).where(Notification.status == NotificationStatus.FAILED))).scalar_one()
    pending = (await session.execute(select(func.count()).where(Notification.status == NotificationStatus.PENDING))).scalar_one()
    lines = [
        "🔔 <b>Уведомления</b>",
        SEP,
        f"Тихие часы: {onoff(qh['enabled'])} · {qh['start']}–{qh['end']} (критичные приходят всегда)",
        f"В очереди: {pending} · не доставлено: {failed}",
        "",
        "<i>Нажмите на тип, чтобы включить или выключить.</i>",
    ]
    rows = [
        [b(f"{'✅' if prefs['kinds'].get(k, True) else '▫️'} {label}", f"ntf:tog:{k}")]
        for k, label in app_settings.NOTIFICATION_KINDS.items()
    ]
    await show(
        cb,
        "\n".join(lines),
        kb(
            *rows,
            [b(f"🌙 Тихие часы: {'выкл' if qh['enabled'] else 'вкл'}", "ntf:quiet"), b("🕘 Время", "ntf:qtime")],
            [b("🧪 Тестовое", "ntf:test"), b("📜 Последние", "ntf:list:1")],
            nav(),
        ),
    )


@router.callback_query(F.data.startswith("ntf:tog:"))
async def toggle_kind(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "settings.manage")
    kind = cb.data.split(":", 2)[2]
    prefs = await app_settings.get_setting(session, "notifications")
    prefs["kinds"][kind] = not prefs["kinds"].get(kind, True)
    await app_settings.set_setting(session, "notifications", prefs, actor)
    await notifications_home(cb, session)


@router.callback_query(F.data == "ntf:quiet")
async def toggle_quiet(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "settings.manage")
    prefs = await app_settings.get_setting(session, "notifications")
    prefs["quiet_hours"]["enabled"] = not prefs["quiet_hours"]["enabled"]
    await app_settings.set_setting(session, "notifications", prefs, actor)
    await notifications_home(cb, session)


@router.callback_query(F.data == "ntf:qtime")
async def quiet_time(cb: CallbackQuery, state: FSMContext, actor: Actor) -> None:
    require(actor, "settings.manage")
    await ask(cb, state, "ntf_quiet", "Тихие часы: <code>23:00-08:00</code>", back="ntf:home")


@on_input("ntf_quiet")
async def quiet_input(message: Message, ctx: dict) -> None:
    start, _, end = message.text.replace(" ", "").partition("-")
    prefs = await app_settings.get_setting(ctx["session"], "notifications")
    prefs["quiet_hours"].update(start=start, end=end)
    await app_settings.set_setting(ctx["session"], "notifications", prefs, ctx["actor"])
    await ctx["state"].clear()
    await message.answer("✅ Сохранено", reply_markup=kb([b("🔔 Уведомления", "ntf:home")]))


@router.callback_query(F.data == "ntf:test")
async def test_notification(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    await notifications.notify(
        session,
        "system",
        "Тестовое уведомление",
        "Если вы это видите — worker отправляет уведомления в Telegram. ✅",
        chat_ids=[cb.from_user.id],
    )
    await cb.answer("Поставлено в очередь. Придёт в течение нескольких секунд, если запущен worker.", show_alert=True)


@router.callback_query(F.data.startswith("ntf:list:"))
async def notification_list(cb: CallbackQuery, session: AsyncSession) -> None:
    page = int(cb.data.split(":")[2])
    total = (await session.execute(select(func.count(Notification.id)))).scalar_one()
    rows = (await session.execute(select(Notification).order_by(Notification.id.desc()).offset((page - 1) * 10).limit(10))).scalars().all()
    icons = {
        NotificationStatus.SENT: "✅",
        NotificationStatus.PENDING: "⏳",
        NotificationStatus.FAILED: "⛔",
        NotificationStatus.SUPPRESSED: "🔕",
    }
    lines = ["📜 <b>Последние уведомления</b>", SEP] + [
        f"{icons[n.status]} {fmt_dt(n.created_at)} · {esc(short(n.title, 50))}" for n in rows
    ]
    await show(cb, "\n".join(lines), kb(pager("ntf:list", page, total, 10), nav("ntf:home")))


# --- 🧾 Журнал операций ----------------------------------------------------------------


@router.callback_query(F.data == "log:home")
async def log_home(cb: CallbackQuery, session: AsyncSession) -> None:
    errors = (await session.execute(select(func.count()).where(SyncRun.status == SyncStatus.FAILED))).scalar_one() + (
        await session.execute(select(func.count()).where(AutomationJob.status == JobStatus.FAILED))
    ).scalar_one()
    await show(
        cb,
        f"🧾 <b>Журнал операций</b>\n{SEP}\nВсе действия администраторов, автоматизации и ошибки интеграций.\nОшибок к разбору: <b>{errors}</b>",
        kb([b("👤 Действия", "log:audit:1"), b("🤖 Автоматизация", "log:auto:1")], [b("🛠 Ошибки интеграций", "log:err")], nav()),
    )


@router.callback_query(F.data.startswith("log:audit:"))
async def audit_log(cb: CallbackQuery, session: AsyncSession) -> None:
    page = int(cb.data.split(":")[2])
    total = (await session.execute(select(func.count(AuditLog.id)))).scalar_one()
    rows = (await session.execute(select(AuditLog).order_by(AuditLog.id.desc()).offset((page - 1) * 12).limit(12))).scalars().all()
    lines = ["👤 <b>Действия</b>", SEP] + [
        f"{fmt_dt(a.created_at)} · <b>{esc(a.actor_name or a.actor_type)}</b> · {esc(a.action)}{(' · ' + esc(a.entity_type) + ' ' + esc(a.entity_id)) if a.entity_type else ''}"
        for a in rows
    ]
    await show(cb, "\n".join(lines) if rows else "👤 Журнал пуст", kb(pager("log:audit", page, total, 12), nav("log:home")))


@router.callback_query(F.data.startswith("log:auto:"))
async def automation_log(cb: CallbackQuery, session: AsyncSession) -> None:
    page = int(cb.data.split(":")[2])
    total = (await session.execute(select(func.count(AutomationLog.id)))).scalar_one()
    rows = (
        (await session.execute(select(AutomationLog).order_by(AutomationLog.id.desc()).offset((page - 1) * 12).limit(12))).scalars().all()
    )
    icons = {"ok": "✅", "skipped": "⏭", "blocked": "🛑", "error": "⛔", "suggested": "💡"}
    lines = ["🤖 <b>Автоматизация</b>", SEP] + [
        f"{icons.get(a.result.value, '•')} {fmt_dt(a.created_at)} · {esc(a.feature)}/{esc(a.action)}: {esc(short(a.message, 70))}"
        for a in rows
    ]
    await show(cb, "\n".join(lines) if rows else "🤖 Событий нет", kb(pager("log:auto", page, total, 12), nav("log:home")))


@router.callback_query(F.data == "log:err")
async def errors(cb: CallbackQuery, session: AsyncSession) -> None:
    runs = (
        (await session.execute(select(SyncRun).where(SyncRun.status == SyncStatus.FAILED).order_by(SyncRun.id.desc()).limit(5)))
        .scalars()
        .all()
    )
    jobs = (
        (
            await session.execute(
                select(AutomationJob).where(AutomationJob.status == JobStatus.FAILED).order_by(AutomationJob.id.desc()).limit(5)
            )
        )
        .scalars()
        .all()
    )
    unknown = (
        (await session.execute(select(SupplierOrder).where(SupplierOrder.status == SupplierOrderStatus.UNKNOWN).limit(5))).scalars().all()
    )
    lines = ["🛠 <b>Ошибки интеграций</b>", SEP, "<b>Синхронизации</b>"]
    lines += [f"• {fmt_dt(r.started_at)} · {esc(r.source)}: {esc(short(r.message, 80))}" for r in runs] or [empty("нет")]
    lines.append("\n<b>Фоновые задачи</b>")
    lines += [f"• #{j.id} {esc(j.kind)} ({j.attempts} попыт.): {esc(short(j.last_error, 80))}" for j in jobs] or [empty("нет")]
    lines.append("\n<b>Закупки с неизвестным результатом</b>")
    lines += [f"• #{so.id}: {esc(short(so.last_error, 80))}" for so in unknown] or [empty("нет")]
    market = get_marketplace()
    lines.append(f"\n<b>PlayerOK</b>: {esc(market.title)} — интеграция по API недоступна (см. «Настройки»)")
    await show(cb, "\n".join(lines), kb(nav("log:home")))


# --- ⚙️ Настройки ---------------------------------------------------------------------


@router.callback_query(F.data == "set:home")
async def settings_home(cb: CallbackQuery, session: AsyncSession) -> None:
    shop = await app_settings.get_setting(session, "shop.profile")
    pipeline = await app_settings.get_setting(session, "orders.auto_pipeline")
    market = get_marketplace()
    s = get_settings()
    from ... import __version__

    lines = [
        "⚙️ <b>Настройки</b>",
        SEP,
        f"Магазин: <b>{esc(shop['name'])}</b>",
        f"Автообработка новых заказов: {onoff(pipeline)}",
        f"Часовой пояс: {esc(s.display_timezone)} · валюта: {esc(s.base_currency)}",
        f"Веб-панель: {esc(s.web_base_url)}",
        f"Версия: {__version__}",
        "",
        f"<b>Интеграция PlayerOK: {esc(market.title)}</b>",
    ]
    for name, label in CAPABILITY_LABELS.items():
        lines.append(f"{'🟢' if market.supports(name) else '🔴'} {label}")
    lines.append(f"\n<i>{esc(market.unavailable_reason)}</i>")
    await show(
        cb,
        "\n".join(lines),
        kb(
            [b("✏️ Название магазина", "set:shop"), b(f"Автообработка: {'выкл' if pipeline else 'вкл'}", "set:pipeline")],
            [b("🗂 Категории и комиссии", "set:cats"), b("🏪 Поставщики", "sup:list")],
            [b("💱 Курсы валют", "prc:fx"), b("⚙️ Автонастройки", "as:home")],
            nav(),
        ),
    )


@router.callback_query(F.data == "set:shop")
async def shop_name(cb: CallbackQuery, state: FSMContext, actor: Actor) -> None:
    require(actor, "settings.manage")
    await ask(cb, state, "set_shop", "Название магазина (подставляется в тексты как {shop})", back="set:home")


@on_input("set_shop")
async def shop_input(message: Message, ctx: dict) -> None:
    profile = await app_settings.get_setting(ctx["session"], "shop.profile")
    profile["name"] = message.text.strip()[:80]
    await app_settings.set_setting(ctx["session"], "shop.profile", profile, ctx["actor"])
    await ctx["state"].clear()
    await message.answer("✅ Сохранено", reply_markup=kb([b("⚙️ Настройки", "set:home")]))


@router.callback_query(F.data == "set:pipeline")
async def pipeline(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "settings.manage")
    value = await app_settings.get_setting(session, "orders.auto_pipeline")
    await app_settings.set_setting(session, "orders.auto_pipeline", not value, actor)
    await settings_home(cb, session)


@router.callback_query(F.data == "set:cats")
async def categories(cb: CallbackQuery, session: AsyncSession) -> None:
    cats = await catalog.list_categories(session)
    rows = [
        [
            b(
                f"{COMPLIANCE_LABELS[c.compliance_status].split()[0]} {short(c.name, 28)} · {c.marketplace_commission_pct.normalize():f}%",
                f"set:cat:{c.id}",
            )
        ]
        for c in cats
    ]
    await show(cb, "🗂 <b>Категории</b>\nКомиссия PlayerOK и статус правил. Нажмите, чтобы изменить.", kb(*rows, nav("set:home")))


@router.callback_query(F.data.regexp(r"^set:cat:\d+$"))
async def category(cb: CallbackQuery, session: AsyncSession) -> None:
    cat = await catalog.get_category(session, int(cb.data.split(":")[2]))
    lines = [
        f"🗂 <b>{esc(cat.name)}</b>",
        SEP,
        f"Комиссия PlayerOK: <b>{cat.marketplace_commission_pct.normalize():f} %</b>",
        f"<i>Источник: {esc(cat.commission_source)}</i>",
        f"Правила: {COMPLIANCE_LABELS[cat.compliance_status]}",
        f"<i>{esc(cat.compliance_note)}</i>",
        f"Оценка риска возвратов: {cat.dispute_risk_pct.normalize():f} %",
    ]
    rows = [[b("✏️ Комиссия", f"set:catfee:{cat.id}")]]
    if cat.compliance_status is ComplianceStatus.NEEDS_REVIEW:
        rows.append(
            [b("✅ Правила проверены — разрешить", f"set:catok:{cat.id}:approved"), b("🛑 Запретить", f"set:catok:{cat.id}:blocked")]
        )
    elif cat.compliance_status is ComplianceStatus.APPROVED:
        rows.append([b("🟡 Вернуть на проверку", f"set:catok:{cat.id}:needs_review")])
    await show(cb, "\n".join(lines), kb(*rows, nav("set:cats")))


@router.callback_query(F.data.startswith("set:catok:"))
async def category_compliance(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "products.manage")
    _, _, cid, status = cb.data.split(":")
    cat = await catalog.get_category(session, int(cid))
    await catalog.update_category(session, cat, {"compliance_status": status}, actor)
    await category(cb, session)


@router.callback_query(F.data.startswith("set:catfee:"))
async def category_fee(cb: CallbackQuery, state: FSMContext, actor: Actor) -> None:
    require(actor, "products.manage")
    cid = int(cb.data.split(":")[2])
    await ask(
        cb,
        state,
        "set_catfee",
        "Комиссия PlayerOK для категории, % (например 10). Если знаете источник — напишите после числа.",
        back=f"set:cat:{cid}",
        category_id=cid,
    )


@on_input("set_catfee")
async def category_fee_input(message: Message, ctx: dict) -> None:
    value, _, source = message.text.strip().partition(" ")
    try:
        pct_value = Decimal(value.replace(",", ".").rstrip("%"))
    except Exception as exc:
        raise DomainError("Нужно число процентов") from exc
    cat = await catalog.get_category(ctx["session"], ctx["category_id"])
    await catalog.update_category(
        ctx["session"], cat, {"marketplace_commission_pct": pct_value, "commission_source": source or None}, ctx["actor"]
    )
    from ...services import jobs

    await jobs.enqueue(ctx["session"], "products.reprice_all", {}, dedupe_key="reprice_all")
    await ctx["state"].clear()
    await message.answer("✅ Комиссия сохранена, цены пересчитываются", reply_markup=kb([b("🗂 Категории", "set:cats")]))
