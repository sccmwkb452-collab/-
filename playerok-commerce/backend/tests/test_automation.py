"""Auto-settings persistence, the autoresponder, reviews, reminders, job queue,
notification delivery and restart recovery."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import select, update

from autocommerce.database.enums import JobStatus, MessageStatus, NotificationStatus, OrderStatus
from autocommerce.database.models import AutomationJob, AutomationLog, Notification
from autocommerce.database.session import dispose_engine, get_sessionmaker, session_scope
from autocommerce.services import app_settings, autosettings, jobs, messages, notifications, orders
from autocommerce.services.audit import CLI
from autocommerce.services.notifications import SendResult
from autocommerce.shared.errors import DomainError
from autocommerce.shared.timeutil import utcnow
from autocommerce.worker.main import Worker, schedule

from .factories import make_product

pytestmark = pytest.mark.usefixtures("seeded")


async def test_all_fourteen_menu_items_exist_in_order():
    async with get_sessionmaker()() as s:
        items = await autosettings.overview(s)
    assert [i["label"] for i in items] == [
        "👋 Приветствие",
        "🤝 Автоподтверждение",
        "🚀 Автоподнятие лотов",
        "🔄 Автовыставление лотов",
        "📦 Автовыдача",
        "🤖 Автоответчик",
        "⏰ Напоминание о подтверждении",
        "⭐ Напоминание об отзыве",
        "💤 Текст, если не в сети",
        "💬 Текст при игноре",
        "💬 Тексты после отзывов",
        "💬 Текст при проблеме",
        "💬 Текст после вашего подтверждения",
        "💬 Текст после подтверждения клиентом",
    ]
    states = {i["code"]: i["integration"]["state"] for i in items}
    assert states["auto_confirm"] == "unavailable"  # PlayerOK has no API: shown honestly
    assert states["greeting"] == "assist"


async def test_settings_survive_restart():
    async with session_scope() as s:
        await autosettings.update(s, "greeting", {"text": "Привет, {buyer}!", "cooldown_hours": "12"}, CLI)
        await autosettings.set_enabled(s, "greeting", True, CLI)
        await app_settings.set_setting(s, "shop.profile", {"name": "Тест-шоп"}, CLI)
    await dispose_engine()  # «restart»: new engine, new connections
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from autocommerce.database.session import set_engine

    from .conftest import TEST_DB

    set_engine(create_async_engine(TEST_DB, poolclass=NullPool))
    async with get_sessionmaker()() as s:
        d = await autosettings.details(s, "greeting")
        assert d["enabled"] and d["config"]["text"] == "Привет, {buyer}!" and d["config"]["cooldown_hours"] == 12
        assert (await app_settings.get_setting(s, "shop.profile"))["name"] == "Тест-шоп"
        assert d["history"], "the change is in the history"


async def test_validation_reset_and_unavailable_toggle():
    async with session_scope() as s:
        with pytest.raises(DomainError):
            await autosettings.update(s, "greeting", {"text": "Привет {unknown_var}"}, CLI)
        with pytest.raises(DomainError):
            await autosettings.update(s, "confirm_reminder", {"max_count": "99"}, CLI)
        with pytest.raises(DomainError):
            await autosettings.set_enabled(s, "auto_confirm", True, CLI)
        await autosettings.update(s, "problem_text", {"text": "Свой текст {order_number}"}, CLI)
        await autosettings.reset(s, "problem_text", CLI)
        d = await autosettings.details(s, "problem_text")
        assert d["config"] == autosettings.feature("problem_text").defaults


async def test_test_action_renders_and_never_sends(sender):
    async with session_scope() as s:
        result = await autosettings.test(s, "review_texts", CLI)
    assert result["ok"] and "player_2026" in result["texts"]["Положительный отзыв"]
    assert sender.sent == []


async def test_emergency_stop_disables_everything():
    async with session_scope() as s:
        await autosettings.set_enabled(s, "greeting", True, CLI)
        await autosettings.set_enabled(s, "autoresponder", True, CLI)
        count = await autosettings.emergency_disable_all(s, CLI, "test")
    assert count == 2
    async with get_sessionmaker()() as s:
        assert await app_settings.automation_stopped(s)
        active, _ = await autosettings.is_active(s, "greeting")
        assert not active


async def test_autoresponder_rules_and_safety(sender):
    pid = await make_product()
    async with session_scope() as s:
        await autosettings.set_enabled(s, "autoresponder", True, CLI)
        order, _ = await orders.create_order(
            s, orders.NewOrder("m-1", [orders.NewItem(pid, 1, D("1500"))], buyer_name="ivan"), CLI, process=False
        )
    async with session_scope() as s:
        order = await orders.get_order(s, order.id)
        status = await messages.record_incoming(s, text="Здравствуйте, где мой заказ?", buyer_name="ivan", order=order, actor=CLI)
        complaint = await messages.record_incoming(s, text="Это обман, код не работает!", buyer_name="ivan", order=order, actor=CLI)
        unknown = await messages.record_incoming(s, text="А вы любите котиков?", buyer_name="ivan", order=order, actor=CLI)
    assert status.status is MessageStatus.SUGGESTED and order.number in status.suggested_reply and "Новый" in status.suggested_reply
    assert complaint.status is MessageStatus.ESCALATED and complaint.problem_hint
    assert unknown.status is MessageStatus.NEW and unknown.problem_hint  # fallback: operator
    # a rule promising completion is not used while the order is not delivered
    async with session_scope() as s:
        messages.validate_rule({"name": "x", "patterns": ["готово?"], "reply_template": "Заказ {order_number} выполнен"})
        from autocommerce.database.models import AutoresponderRule

        s.add(
            AutoresponderRule(
                name="Обещание", priority=1, patterns=["готово"], action="reply", reply_template="Заказ {order_number} выполнен"
            )
        )
    async with session_scope() as s:
        order = await orders.get_order(s, order.id)
        result = await messages.test_rules(s, "готово?", order)
    assert result["action"] == "manual" and result["reply"] is None
    async with get_sessionmaker()() as s:
        notes = (await s.execute(select(Notification).where(Notification.kind == "customer_message"))).scalars().all()
    assert len(notes) == 3 and all("PlayerOK без API" in n.body for n in notes)
    assert not any("✍️ Ответить" in str(n.buttons) for n in notes)  # no reply button without a sending API


async def test_regex_rule_validation():
    with pytest.raises(DomainError):
        messages.validate_rule({"name": "bad", "match_type": "regex", "patterns": ["(a+)+$"]})
    with pytest.raises(DomainError):
        messages.validate_rule({"name": "bad", "match_type": "regex", "patterns": ["("]})
    ok = messages.validate_rule(
        {"name": "ok", "match_type": "regex", "patterns": [r"\bкод\b"], "reply_template": "Код придёт после оплаты"}
    )
    assert ok["patterns"] == [r"\bкод\b"]


async def test_review_stops_review_reminder(sender):
    pid = await make_product()
    async with session_scope() as s:
        await autosettings.set_enabled(s, "review_reminder", True, CLI)
        await autosettings.set_enabled(s, "review_texts", True, CLI)
        order, _ = await orders.create_order(
            s, orders.NewOrder("rv-1", [orders.NewItem(pid, 1, D("1500"))], buyer_name="olga"), CLI, process=False
        )
        order = await orders.get_order(s, order.id, lock=True)
        order.status = OrderStatus.COMPLETED
    async with session_scope() as s:
        order = await orders.get_order(s, order.id)
        review = await messages.record_review(s, order=order, rating=5, text="Быстро, спасибо", actor=CLI)
        assert review.sentiment.value == "positive"
    async with session_scope() as s:
        await orders.send_reminder(s, order.id, "review", 1)
    async with get_sessionmaker()() as s:
        hints = (
            (await s.execute(select(AutomationLog).where(AutomationLog.feature == "review_reminder", AutomationLog.action == "suggest")))
            .scalars()
            .all()
        )
    assert hints == []  # no reminder after the review


async def test_job_queue_dedupe_backoff_and_restart_recovery():
    async with session_scope() as s:
        a = await jobs.enqueue(s, "noop", {}, dedupe_key="same")
        b = await jobs.enqueue(s, "noop", {}, dedupe_key="same")
    assert a is not None and b is None
    async with session_scope() as s:
        claimed = await jobs.claim(s, "w1")
        assert [j.id for j in claimed] == [a]
    async with session_scope() as s:
        assert await jobs.claim(s, "w2") == []  # nobody else takes a running job
    # the worker «crashed»: lease expires, recovery puts it back
    async with session_scope() as s:
        await s.execute(update(AutomationJob).values(locked_until=utcnow() - timedelta(seconds=1)))
    async with session_scope() as s:
        assert await jobs.recover_stale(s) == 1
    async with session_scope() as s:
        job = (await jobs.claim(s, "w2"))[0]
        assert job.attempts == 2
        retried = await jobs.fail(s, job, "boom")
        assert retried and job.status is JobStatus.QUEUED and job.run_after > utcnow()
        job.attempts = job.max_attempts
        assert not await jobs.fail(s, job, "boom again")
        assert job.status is JobStatus.FAILED


async def test_periodic_schedule_is_idempotent():
    now = utcnow()
    async with session_scope() as s:
        first = await schedule(s, now)
    async with session_scope() as s:
        second = await schedule(s, now)
    assert first > 0 and second == 0


async def test_worker_runs_order_job_and_sends_notifications(sender):
    pid = await make_product()
    async with session_scope() as s:
        from autocommerce.services import inventory

        product = await orders.get_product(s, pid)
        await inventory.add_codes(s, product, ["W-1234-5678"], CLI, is_test=True)
        order, _ = await orders.create_order(s, orders.NewOrder("w-1", [orders.NewItem(pid, 1, D("1500"))], is_test=True), CLI)
    worker = Worker("test-worker")
    await worker.run_job_batch()
    async with session_scope() as s:
        await notifications.send_pending(s)
    async with get_sessionmaker()() as s:
        refreshed = await orders.get_order(s, order.id)
        assert refreshed.status is OrderStatus.READY_FOR_DELIVERY
    texts = [t for _, t, _ in sender.sent]
    assert any("Новый заказ" in t for t in texts) and any("Готов к выдаче" in t for t in texts)
    assert not any("W-1234-5678" in t for t in texts)  # codes never travel in notifications


async def test_notification_flood_limit_and_permanent_failure(sender):
    async with session_scope() as s:
        await notifications.notify(s, "system", "A", "a")
        await notifications.notify(s, "system", "B", "b")
    sender.script = [SendResult(False, retry_after=7, error="rate limited")]
    async with session_scope() as s:
        stats = await notifications.send_pending(s)
    assert stats["retry"] == 1 and stats["sent"] == 0  # batch stops on the flood limit
    async with get_sessionmaker()() as s:
        rows = (await s.execute(select(Notification).order_by(Notification.id))).scalars().all()
        assert rows[0].status is NotificationStatus.PENDING and rows[0].next_attempt_at > utcnow()
    sender.script = [SendResult(False, permanent=True, error="Forbidden: bot was blocked by the user")]
    async with session_scope() as s:
        stats = await notifications.send_pending(s)
    assert stats["failed"] == 1


async def test_disabled_kind_is_suppressed_but_recorded(sender):
    async with session_scope() as s:
        prefs = await app_settings.get_setting(s, "notifications")
        prefs["kinds"]["report"] = False
        await app_settings.set_setting(s, "notifications", prefs, CLI)
        await notifications.notify(s, "report", "Отчёт", "текст")
    async with session_scope() as s:
        await notifications.send_pending(s)
    assert sender.sent == []
    async with get_sessionmaker()() as s:
        row = (await s.execute(select(Notification))).scalar_one()
        assert row.status is NotificationStatus.SUPPRESSED
