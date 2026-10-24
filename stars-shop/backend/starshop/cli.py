"""Operational commands.

python -m starshop.cli seed                 # demo catalog (only if empty)
python -m starshop.cli admin-add 123 --role owner
python -m starshop.cli admin-link 123       # one-time admin login URL
python -m starshop.cli check                # configuration report (no secrets)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database.enums import AdminRole, ProductKind
from .database.models import AdminUser, Product
from .database.session import dispose_engine, session_scope
from .delivery.registry import get_delivery_provider
from .payments.registry import KNOWN_PROVIDERS, get_payment_provider
from .services.admin_auth import ensure_bootstrap_admins, issue_login_token

# Starting examples only — real prices are managed in the admin panel.
DEMO_PACKAGES = [
    (50, "89.00"),
    (100, "169.00"),
    (250, "409.00"),
    (500, "799.00"),
    (1000, "1549.00"),
    (2500, "3790.00"),
    (5000, "7490.00"),
]
# Telegram Premium: months, price.
DEMO_PREMIUM = ((3, "1590.00"), (6, "2290.00"), (12, "3990.00"))


async def seed_catalog(session: AsyncSession) -> int:
    """Demo catalog for an empty shop. Returns how many products already existed."""
    count = await session.scalar(select(func.count()).select_from(Product))
    if count:
        return count
    for index, (stars, price) in enumerate(DEMO_PACKAGES):
        session.add(
            Product(
                kind=ProductKind.package,
                stars_amount=stars,
                price=Decimal(price),
                is_popular=stars == 500,
                sort_order=index * 10,
            )
        )
    session.add(
        Product(
            kind=ProductKind.custom,
            title="Своё количество",
            price_per_star=Decimal("1.65"),
            min_stars=50,
            max_stars=100_000,
            sort_order=1000,
        )
    )
    for index, (months, price) in enumerate(DEMO_PREMIUM):
        session.add(Product(kind=ProductKind.premium, premium_months=months, price=Decimal(price), sort_order=2000 + index * 10))
    return 0


async def seed() -> None:
    async with session_scope() as session:
        await ensure_bootstrap_admins(session)
        count = await seed_catalog(session)
    print(f"catalog already has {count} products — skipped" if count else "demo catalog created")


async def admin_add(telegram_id: int, role: str, name: str | None) -> None:
    async with session_scope() as session:
        admin = (await session.execute(select(AdminUser).where(AdminUser.telegram_id == telegram_id))).scalar_one_or_none()
        if admin is None:
            session.add(AdminUser(telegram_id=telegram_id, role=AdminRole(role), display_name=name, is_active=True))
            print("admin created")
        else:
            admin.role = AdminRole(role)
            admin.is_active = True
            print("admin updated")


async def admin_link(telegram_id: int) -> None:
    async with session_scope() as session:
        await ensure_bootstrap_admins(session)
        await session.flush()
        admin = (
            await session.execute(select(AdminUser).where(AdminUser.telegram_id == telegram_id, AdminUser.is_active.is_(True)))
        ).scalar_one_or_none()
        if admin is None:
            print("no active admin with this telegram id", file=sys.stderr)
            raise SystemExit(1)
        token = await issue_login_token(session, admin)
    print(f"{get_settings().admin_url}login#token={token}")


def check() -> None:
    s = get_settings()
    print(f"env={s.app_env} mode={s.app_mode} allow_production={s.allow_production}")
    print(f"public_base_url={s.public_base_url} webapp={s.webapp_url} admin={s.admin_url}")
    print(
        f"bot_token={'set' if s.bot_token.get_secret_value() else 'MISSING'} bot_username={s.bot_username or 'MISSING'} mode={s.bot_mode}"
    )
    print(f"admins={s.admin_telegram_ids or 'NONE'} currency={s.shop_currency} redis={'set' if s.redis_url else 'not set'}")
    for name in KNOWN_PROVIDERS:
        p = get_payment_provider(name)
        print(f"payment {name}: enabled={name in s.payment_providers} configured={p.is_configured()}")
    d = get_delivery_provider()
    print(f"delivery {d.name}: configured={d.is_configured()} demo={d.is_demo} idempotent={d.idempotent}")
    if s.secret_key.get_secret_value().startswith("change-me"):
        print("WARNING: SECRET_KEY is the default value")


def main() -> None:
    parser = argparse.ArgumentParser(prog="starshop")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    p_add = sub.add_parser("admin-add")
    p_add.add_argument("telegram_id", type=int)
    p_add.add_argument("--role", choices=[r.value for r in AdminRole], default="support")
    p_add.add_argument("--name")
    p_link = sub.add_parser("admin-link")
    p_link.add_argument("telegram_id", type=int)
    sub.add_parser("check")
    args = parser.parse_args()

    async def run() -> None:
        try:
            if args.cmd == "seed":
                await seed()
            elif args.cmd == "admin-add":
                await admin_add(args.telegram_id, args.role, args.name)
            elif args.cmd == "admin-link":
                await admin_link(args.telegram_id)
        finally:
            await dispose_engine()

    if args.cmd == "check":
        check()
    else:
        asyncio.run(run())


if __name__ == "__main__":
    main()
