# Telegram NFT Gift Bot

Бот для покупки, хранения и дарения NFT-подарков в Telegram.

## Стек технологий

- **Python 3.11+**
- **aiogram 3** — фреймворк для Telegram-ботов
- **PostgreSQL** — основная база данных
- **SQLAlchemy 2 (async)** — ORM с поддержкой asyncpg
- **pydantic-settings** — типизированная конфигурация через `.env`

## Структура проекта

```
tg-bot/
├── bot/
│   ├── main.py              # Точка входа, сборка Dispatcher
│   ├── config.py            # Конфигурация из .env
│   ├── logging_config.py    # Настройка логирования
│   ├── database/
│   │   ├── models.py        # SQLAlchemy-модели (User, Subscription, NFTGift, Transaction)
│   │   └── session.py       # Движок и фабрика сессий
│   ├── handlers/
│   │   ├── start.py         # /start, /menu
│   │   ├── menu.py          # Callback-хендлеры главного меню
│   │   └── errors.py        # Глобальный обработчик ошибок
│   ├── keyboards/
│   │   └── main_menu.py     # Главное меню и кнопка «Назад»
│   └── middlewares/
│       ├── db.py            # Инжекция сессии БД в хендлеры
│       └── user.py          # Авто-регистрация/обновление пользователя
├── logs/                    # Файлы логов (создаются автоматически)
├── .env.example             # Пример файла конфигурации
├── requirements.txt
└── README.md
```

## Быстрый старт

### 1. Клонировать репозиторий и перейти в директорию бота

```bash
cd tg-bot
```

### 2. Создать и активировать виртуальное окружение

```bash
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# или
.venv\Scripts\activate         # Windows
```

### 3. Установить зависимости

```bash
pip install -r requirements.txt
```

### 4. Настроить переменные окружения

```bash
cp .env.example .env
```

Заполни `.env`:

| Переменная | Описание | Пример |
|---|---|---|
| `BOT_TOKEN` | Токен от [@BotFather](https://t.me/BotFather) | `123456:ABC-DEF...` |
| `BOT_ADMIN_IDS` | Telegram ID администраторов (через запятую) | `123456789,987654321` |
| `DATABASE_URL` | URL подключения к PostgreSQL (asyncpg) | `postgresql+asyncpg://user:pass@localhost:5432/nft_gifts_db` |
| `DEBUG` | Включить SQL-логи и отладку | `false` |
| `LOG_LEVEL` | Уровень логирования | `INFO` |
| `SUPPORT_USERNAME` | Username аккаунта поддержки | `my_support` |

### 5. Создать базу данных PostgreSQL

```bash
createdb nft_gifts_db
# или через psql:
psql -c "CREATE DATABASE nft_gifts_db;"
```

> Таблицы создаются автоматически при первом запуске бота (`CREATE TABLE IF NOT EXISTS`).

### 6. Запустить бота

```bash
python -m bot.main
```

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | Приветствие и главное меню |
| `/menu` | Открыть главное меню |

## Главное меню

- **💎 Купить подписку** — оформление/управление подпиской
- **🎁 NFT-подарки** — каталог и коллекция NFT
- **👤 Мой аккаунт** — профиль, статистика
- **📋 История операций** — последние 10 транзакций
- **🆘 Поддержка** — контакт поддержки

## Модели базы данных

- **User** — пользователь Telegram (авто-регистрация при первом обращении)
- **Subscription** — подписки пользователей (active / expired / cancelled)
- **NFTGift** — NFT-подарки с атрибутами (rarity, token_id, transferable)
- **Transaction** — история операций (subscription / nft_purchase / nft_gift / refund)

## Логирование

Логи пишутся одновременно в `stdout` и в файл `logs/bot.log`. Ротация не настроена — при необходимости подключи `RotatingFileHandler`.

## Планируемые функции

- [ ] Платёжная система (Stars / Telegram Payments)
- [ ] Каталог NFT с фильтрами и пагинацией
- [ ] Передача NFT-подарков другим пользователям
- [ ] Панель администратора
- [ ] Уведомления и рассылки
