# NFT Gift Bot

Telegram-бот для управления NFT-подарками с платной подпиской.

## Стек

| Компонент | Технология |
|---|---|
| Бот | Python 3.12, aiogram 3.13 |
| База данных | PostgreSQL 16 + SQLAlchemy 2 (async) |
| Миграции | Alembic |
| Кэш / FSM | Redis 7 |
| Конфигурация | pydantic-settings + .env |
| Контейнеры | Docker Compose |

## Архитектура

```
nft-gift-bot/
├── main.py                  # Точка входа
├── logging_setup.py         # Настройка логирования
├── config/
│   └── settings.py          # Все переменные окружения (pydantic-settings)
├── bot/
│   ├── handlers/            # aiogram-роутеры
│   │   ├── start.py         #   /start, /menu
│   │   └── errors.py        #   Глобальный обработчик ошибок
│   ├── middlewares/
│   │   ├── db.py            #   Инжекция AsyncSession
│   │   └── user.py          #   Авто-регистрация пользователя
│   ├── filters/
│   │   └── admin.py         #   Фильтр: только администраторы
│   └── keyboards/
│       └── main_menu.py     #   Главное меню (InlineKeyboard)
├── database/
│   ├── base.py              # DeclarativeBase с created_at/updated_at
│   ├── session.py           # Движок asyncpg, фабрика сессий
│   ├── models/
│   │   ├── user.py          #   User
│   │   ├── subscription.py  #   Subscription
│   │   ├── gift.py          #   NFT Gift
│   │   └── transaction.py   #   Transaction
│   └── repositories/
│       ├── base.py          #   Generic CRUD
│       ├── user_repo.py     #   UserRepository
│       └── subscription_repo.py
├── services/
│   ├── user_service.py      # Логика пользователей
│   └── subscription_service.py
├── payments/
│   └── base.py              # Абстрактный PaymentProvider
├── admin/
│   └── router.py            # /admin команды
├── gift_manager/
│   └── client.py            # Обёртка над Telegram Gift API
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_schema.py
├── docker/
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

## Быстрый старт

### 1. Подготовка

```bash
git clone <repo>
cd nft-gift-bot
cp .env.example .env
```

Заполни `.env`:
- `BOT_TOKEN` — токен от [@BotFather](https://t.me/BotFather)
- `POSTGRES_PASSWORD` — придумай надёжный пароль
- `BOT_ADMIN_IDS` — твой Telegram ID (узнай у [@userinfobot](https://t.me/userinfobot))

### 2. Запуск через Docker Compose

```bash
# Поднять PostgreSQL + Redis
docker compose up -d db redis

# Применить миграции
docker compose run --rm --profile tools migrate

# Запустить бота
docker compose up -d bot

# Логи
docker compose logs -f bot
```

### 3. Локальный запуск (без Docker)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Убедись, что PostgreSQL и Redis запущены локально, затем:
python main.py
```

## Миграции

```bash
# Применить все миграции
alembic upgrade head

# Откатить последнюю
alembic downgrade -1

# Создать новую миграцию (autogenerate)
alembic revision --autogenerate -m "add some_table"

# История
alembic history --verbose
```

## Переменные окружения

| Переменная | Обязательная | Описание |
|---|---|---|
| `BOT_TOKEN` | ✅ | Токен бота от @BotFather |
| `POSTGRES_PASSWORD` | ✅ | Пароль PostgreSQL |
| `BOT_ADMIN_IDS` | — | ID администраторов через запятую |
| `POSTGRES_HOST` | — | Хост БД (default: `db`) |
| `REDIS_HOST` | — | Хост Redis (default: `redis`) |
| `APP_ENV` | — | `development` / `staging` / `production` |
| `LOG_LEVEL` | — | `DEBUG` / `INFO` / `WARNING` |
| `DEBUG_SQL` | — | Логировать SQL-запросы (`false`) |
| `SUPPORT_USERNAME` | — | Username аккаунта поддержки |

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | Приветствие и главное меню |
| `/menu` | Открыть главное меню |
| `/admin` | Панель администратора (только для admin IDs) |

## Разработка

- **Новый хендлер** → создай файл в `bot/handlers/`, зарегистрируй роутер в `bot/handlers/__init__.py`
- **Новая модель** → добавь в `database/models/`, импортируй в `database/models/__init__.py`, создай репозиторий в `database/repositories/`, сгенерируй миграцию
- **Новый сервис** → добавь в `services/`, используй репозиторий
- **Новый провайдер платежей** → унаследуй от `payments.base.BasePaymentProvider`
