"""Command line: initial setup, administrators, keys, configuration check.

python -m autocommerce.cli init                 # migrations + initial data
python -m autocommerce.cli create-admin --email … --name … [--role owner]
python -m autocommerce.cli check-config         # prints problems, exit 1 if any
python -m autocommerce.cli gen-key              # new CREDENTIALS_KEY
python -m autocommerce.cli rotate-keys          # re-encrypt with the first key
python -m autocommerce.cli sync                 # FX + supplier catalogues now
python -m autocommerce.cli health worker        # health check (db | worker | bot), exit 1 if dead
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

from .config import BACKEND_DIR, get_settings
from .database.enums import RoleCode


def _migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["skip_logging"] = True
    command.upgrade(cfg, "head")


async def _init() -> None:
    from .database.session import session_scope
    from .services import bootstrap

    async with session_scope() as session:
        counts = await bootstrap.seed(session)
    print(f"Начальные данные: {counts}")


async def _create_admin(email: str, name: str, role: str, password: str) -> None:
    from sqlalchemy import select

    from .database.models import User
    from .database.session import session_scope
    from .services import auth
    from .services.audit import CLI

    async with session_scope() as session:
        existing = (await session.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
        if existing:
            await auth.set_password(session, existing, password, CLI)
            existing.is_active = True
            print(f"Пароль пользователя {email} обновлён, его сессии завершены")
            return
        await auth.create_user(session, email=email, password=password, display_name=name, role=RoleCode(role), actor=CLI)
        print(f"Создан пользователь {email} ({role})")


async def _rotate() -> None:
    from sqlalchemy import select

    from .database.models import DigitalCode, User
    from .database.session import session_scope
    from .services import credentials
    from .shared import crypto

    async with session_scope() as session:
        n = await credentials.rotate_encryption(session)
        codes = (await session.execute(select(DigitalCode))).scalars().all()
        for code in codes:
            code.code_enc = crypto.rotate(code.code_enc)
        users = (await session.execute(select(User).where(User.totp_secret_enc.is_not(None)))).scalars().all()
        for user in users:
            user.totp_secret_enc = crypto.rotate(user.totp_secret_enc)
    print(f"Перешифровано: ключей интеграций {n}, кодов {len(codes)}, секретов 2FA {len(users)}")


async def _sync() -> None:
    from .database.session import session_scope
    from .services import fx, suppliers

    async with session_scope() as session:
        run = await fx.sync_cbr(session)
        print(f"ЦБ РФ: {run.status.value} — {run.message}")
    async with session_scope() as session:
        for run in await suppliers.sync_all(session):
            print(f"{run.source}: {run.status.value} — {run.message}")


def check_config() -> list[str]:
    settings = get_settings()
    problems = settings.config_problems()
    if not settings.bot_token.get_secret_value():
        problems.append("BOT_TOKEN не задан — Telegram-бот и уведомления не работают")
    if not settings.owner_telegram_ids:
        problems.append("OWNER_TELEGRAM_IDS не задан — бот никого не пустит, уведомления не придут")
    storage = Path(settings.storage_dir)
    try:
        storage.mkdir(parents=True, exist_ok=True)
        probe = storage / ".write-test"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        problems.append(f"Каталог хранилища {storage} недоступен для записи: {exc}")
    if not (settings.assets_dir / "fonts" / "Inter-Regular.otf").exists():
        problems.append("Нет шрифтов в assets/fonts — генератор изображений не будет работать")
    return problems


async def _health(component: str) -> int:
    """Exit code for container health checks: 0 when the component is alive."""
    import socket

    from .database.session import check_database, session_scope
    from .services import health

    db_ok, message = await check_database()
    if not db_ok:
        print(f"✖ База данных недоступна: {message}")
        return 1
    if component == "db":
        print("✔ База данных доступна")
        return 0
    async with session_scope() as session:
        state = (await health.status(session))[component]
    # the heartbeat row is shared by all instances: require that this host wrote it
    mine = (state["instance"] or "").startswith(f"{socket.gethostname()}:")
    if state["ok"] and mine:
        print(f"✔ {component}: сигнал {state['last_seen_at']}")
        return 0
    print(f"✖ {component}: нет свежего сигнала от этого экземпляра (последний: {state['last_seen_at']}, {state['instance']})")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="autocommerce")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("migrate")
    admin = sub.add_parser("create-admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", default="Владелец")
    admin.add_argument("--role", default="owner", choices=[r.value for r in RoleCode])
    sub.add_parser("check-config")
    sub.add_parser("gen-key")
    sub.add_parser("rotate-keys")
    sub.add_parser("sync")
    health_cmd = sub.add_parser("health")
    health_cmd.add_argument("component", choices=["db", "worker", "bot"])
    args = parser.parse_args(argv)

    if args.cmd == "gen-key":
        from .shared.crypto import generate_key

        print(generate_key())
        return 0
    if args.cmd == "check-config":
        problems = check_config()
        for p in problems:
            print(f"✖ {p}")
        if not problems:
            print("✔ Конфигурация в порядке")
        return 1 if any("BOT_TOKEN" not in p and "OWNER_TELEGRAM_IDS" not in p for p in problems) else 0
    if args.cmd == "migrate":
        _migrate()
        return 0
    if args.cmd == "init":
        _migrate()
        asyncio.run(_init())
        return 0
    if args.cmd == "create-admin":
        password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Пароль (мин. 10 символов, строчные, заглавные, цифра): ")
        asyncio.run(_create_admin(args.email, args.name, args.role, password))
        return 0
    if args.cmd == "rotate-keys":
        asyncio.run(_rotate())
        return 0
    if args.cmd == "sync":
        asyncio.run(_sync())
        return 0
    if args.cmd == "health":
        return asyncio.run(_health(args.component))
    return 1


if __name__ == "__main__":
    sys.exit(main())
