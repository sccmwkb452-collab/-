# PlayerOK Auto Commerce

Система для магазина цифровых товаров на PlayerOK: Telegram-бот, закрытая веб-панель, учёт заказов и выдачи кодов, закупка у поставщиков с лимитами, расчёт цен без убытка, исследование товаров, объявления с картинками по вашим шаблонам, аналитика.

| | |
| --- | --- |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, PostgreSQL 16, Redis (необязательно) |
| Бот | aiogram 3 — 16 разделов меню, 14 автонастроек |
| Воркер | очередь задач в PostgreSQL: заказы, закупки, синхронизация, цены, уведомления, отчёты |
| Панель | Next.js 16, TypeScript, Tailwind 4, Radix UI, Recharts — 20+ страниц на реальных данных |
| Развёртывание | Docker Compose + Caddy (HTTPS) на VPS, панель на Vercel; альтернатива — systemd |

## Что работает и где ограничения

- **PlayerOK — ручной режим с подсказками.** Открытого API у площадки нет, а неофициальный способ обходит её защиту — система его не использует. Заказы и сообщения вносятся в бот/панель (или CSV), публикация — по готовой инструкции с кнопками копирования. Подробно — [docs/OPERATIONS.md](docs/OPERATIONS.md).
- **Поставщики:** курсы ЦБ РФ и цены Fragment работают; VexBoost и Reloadly — адаптеры готовы, нужны ключи; KOSell заблокирован (нарушает правила Steam). Источники и даты проверки — [docs/RESEARCH.md](docs/RESEARCH.md).
- **Тестовый режим по умолчанию:** закупки и публикации только имитируются.

## Структура

```
playerok-commerce/
├── backend/
│   ├── autocommerce/      api, bot, worker, services, integrations, imaging, database, shared, cli.py
│   ├── migrations/        Alembic
│   ├── assets/            шрифты (OFL), шаблоны изображений (demo, originals)
│   ├── tests/             96 тестов на PostgreSQL
│   ├── Dockerfile
│   └── .env.example
├── web/                   панель Next.js (+ Dockerfile для варианта без Vercel)
├── deploy/                Caddyfile, systemd-юниты, scripts/{backup,restore,update}.sh
├── docs/                  DEPLOY, OPERATIONS, SECURITY, ARCHITECTURE, IMAGES, RESEARCH
├── docker-compose.yml
└── IMPLEMENTATION_PLAN.md
```

## Запуск для разработки

```bash
# PostgreSQL 16 локально: пользователь pac/pac, базы pac и pac_test
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env        # APP_ENV=development, DATABASE_URL, BOT_TOKEN, OWNER_TELEGRAM_IDS
.venv/bin/python -m autocommerce.cli init
ADMIN_PASSWORD='…' .venv/bin/python -m autocommerce.cli create-admin --email you@example.com
.venv/bin/uvicorn autocommerce.api.app:app --reload     # API :8000
.venv/bin/python -m autocommerce.worker                  # воркер
.venv/bin/python -m autocommerce.bot                     # бот

cd ../web && npm ci && npm run dev                       # панель :3000 (BACKEND_URL по умолчанию http://127.0.0.1:8000)
```

## Проверки

```bash
cd backend && .venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/ruff format --check .
cd web && npm run typecheck && npm run lint && npm run build
```

## Документация

- [Развёртывание](docs/DEPLOY.md) — VPS + Vercel, без Docker, обновления, резервные копии
- [Эксплуатация](docs/OPERATIONS.md) — заказы, закупки, объявления, режимы, аварийная остановка
- [Безопасность](docs/SECURITY.md) — секреты, шифрование, роли, ротация ключей
- [Архитектура](docs/ARCHITECTURE.md) — компоненты, данные, надёжность, формулы цен
- [Изображения](docs/IMAGES.md) — шаблоны и формат разметки
- [Исследование](docs/RESEARCH.md) — PlayerOK, поставщики, источники
