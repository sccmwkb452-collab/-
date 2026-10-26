# Развёртывание

Система состоит из двух частей:

| Часть | Где работает | Почему |
| --- | --- | --- |
| **Веб-панель** (Next.js) | Vercel | Статические страницы и прокси `/api` → backend. Постоянных процессов не требует |
| **Backend**: API (FastAPI), воркер, Telegram-бот, PostgreSQL, Redis | Постоянный сервер (VPS) | Бот и воркер — долгоживущие процессы: на Vercel они работать не могут |

Панель обращается к API через собственный адрес (`/api/*` переписывается на `BACKEND_URL`), поэтому cookie сессии остаётся «своей» для домена панели, CORS не нужен.

Проверенный путь — **Docker Compose на VPS + Vercel для панели**. Вся связка (БД, миграции, API, воркер, бот, Caddy с HTTPS, панель) собрана и запущена в тестовом окружении: все сервисы в статусе `healthy`, вход в панель, сквозной сценарий заказа, резервное копирование и восстановление проверены.

---

## 1. Сервер

Подойдёт любой VPS с Ubuntu 22.04/24.04: 2 vCPU, 2–4 ГБ RAM, 30 ГБ диска.

```bash
# Docker (официальный скрипт)
curl -fsSL https://get.docker.com | sh

# код
sudo mkdir -p /opt && cd /opt
sudo git clone <адрес репозитория> playerok-src
sudo ln -s /opt/playerok-src/playerok-commerce /opt/playerok-commerce
cd /opt/playerok-commerce
```

DNS: создайте A-запись `api.<ваш-домен>` → IP сервера. Порты 80 и 443 должны быть открыты — Caddy сам получит сертификат Let's Encrypt.

## 2. Настройки

```bash
cp .env.example .env                    # переменные compose
cp backend/.env.example backend/.env    # настройки приложения и секреты
chmod 600 .env backend/.env
```

В `.env` (рядом с `docker-compose.yml`):

| Переменная | Значение |
| --- | --- |
| `POSTGRES_PASSWORD` | `openssl rand -hex 24` |
| `API_DOMAIN` | `api.<ваш-домен>` |

В `backend/.env` обязательно:

| Переменная | Как получить |
| --- | --- |
| `SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `CREDENTIALS_KEY` | `docker compose run --rm migrate python -m autocommerce.cli gen-key` (после шага 3) |
| `WEB_BASE_URL` | адрес панели, например `https://panel.<ваш-домен>` или `https://<проект>.vercel.app` |
| `TRUSTED_PROXY_HOPS` | `2` (Vercel → Caddy → API) |
| `BOT_TOKEN` | токен от @BotFather |
| `BOT_USERNAME` | имя бота без `@` |
| `OWNER_TELEGRAM_IDS` | ваш Telegram ID (команда `/id` в боте) |

Без `SECRET_KEY` (≥ 32 символов) и `CREDENTIALS_KEY` API, воркер и бот в режиме `APP_ENV=production` **откажутся запускаться** и напишут, чего не хватает.

`APP_MODE=test` (по умолчанию) — закупки и публикации не выполняются по-настоящему. Боевой режим описан в [OPERATIONS.md](OPERATIONS.md#боевой-режим).

## 3. Запуск

```bash
docker compose build
docker compose run --rm migrate python -m autocommerce.cli gen-key   # → CREDENTIALS_KEY в backend/.env
docker compose up -d
docker compose ps          # db, redis, api, worker, bot — healthy; caddy — Up
```

Порядок запуска задан в compose: БД → миграции и начальные данные (`migrate`) → API, воркер, бот → Caddy.

Первый пользователь — владелец (только из консоли):

```bash
docker compose run --rm migrate python -m autocommerce.cli create-admin --email you@example.com --name "Ваше имя"
```

Пароль запрашивается без отображения: не короче 10 символов, строчные и заглавные буквы, цифра.

Проверка:

```bash
curl https://api.<ваш-домен>/api/v1/health/ready
# {"ok":true,"database":true,"worker":true,"bot":true,"mode":"test"}
docker compose run --rm migrate python -m autocommerce.cli check-config
```

## 4. Панель на Vercel

1. Vercel → **Add New → Project** → импортируйте репозиторий.
2. **Root Directory**: `playerok-commerce/web`. Framework определится сам (Next.js).
3. **Environment Variables**: `BACKEND_URL` = `https://api.<ваш-домен>` (без `/` в конце) для Production и Preview.
4. **Deploy**.
5. Свой домен (необязательно): Project → Settings → Domains → `panel.<ваш-домен>`; затем обновите `WEB_BASE_URL` в `backend/.env` и `docker compose up -d`.

Адреса `/api/*` переписываются на `BACKEND_URL` **во время сборки**: после смены `BACKEND_URL` нужен Redeploy. Сборка на Vercel без `BACKEND_URL` вида `https://…` намеренно падает с понятной ошибкой — чтобы панель не ушла в работу «в никуда».

Проверка после деплоя: откройте `https://<панель>/login`, войдите, на главной в шапке должны быть «Воркер работает» и «Бот работает».

## 5. Всё на одном сервере (без Vercel)

```bash
# в .env
PANEL_DOMAIN=panel.<ваш-домен>
CADDYFILE=./deploy/Caddyfile.panel
docker compose --profile panel up -d --build
```

Панель собирается из `web/Dockerfile` и работает за тем же Caddy. В этом случае `TRUSTED_PROXY_HOPS=1`.

## 6. Обновление и резервные копии

```bash
deploy/scripts/update.sh      # git pull → резервная копия → сборка → миграции → перезапуск → ожидание healthy
deploy/scripts/backup.sh      # БД (pg_dump, формат custom, проверяется pg_restore --list) + изображения
deploy/scripts/restore.sh backups/pac-….dump backups/storage-….tar.gz --yes
```

`restore.sh` заменяет текущую базу, поэтому без `--yes` ничего не делает, а перед восстановлением сам делает копию текущего состояния. Ежедневная копия через cron:

```cron
20 4 * * * /opt/playerok-commerce/deploy/scripts/backup.sh >> /var/log/pac-backup.log 2>&1
```

Храните копии и вне сервера (например, `rclone` в объектное хранилище): копия на том же диске не спасёт от потери сервера.

## 7. Без Docker (systemd)

```bash
sudo apt install python3.12-venv postgresql-16 redis-server caddy
sudo useradd --system --home /opt/playerok-commerce pac
cd /opt/playerok-commerce/backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # DATABASE_URL=postgresql+asyncpg://pac:<пароль>@localhost:5432/pac, TRUSTED_PROXY_HOPS=1 или 2
sudo -u postgres createuser -P pac && sudo -u postgres createdb -O pac pac
.venv/bin/python -m autocommerce.cli init
.venv/bin/python -m autocommerce.cli create-admin --email you@example.com
sudo chown -R pac:pac storage
sudo cp ../deploy/systemd/pac-*.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now pac-api pac-worker pac-bot
```

Caddy: `api.<ваш-домен> { reverse_proxy 127.0.0.1:8000 }`.

## 8. Управляемые базы данных

`DATABASE_URL` принимает и обычные адреса `postgres://…` (Neon, Supabase, Railway): драйвер и параметры SSL подставляются автоматически. Нужен PostgreSQL 14+.

## 9. Что проверить после развёртывания

- [ ] `https://api.<домен>/api/v1/health/ready` → `database`, `worker`, `bot` = `true`
- [ ] вход в панель, включена двухфакторная аутентификация (раздел «Безопасность»)
- [ ] бот отвечает на `/start` с вашего аккаунта и не отвечает с чужого
- [ ] в «Уведомлениях» приходит тестовое событие (например, создайте тестовый заказ)
- [ ] `backup.sh` отработал, копия лежит вне сервера
- [ ] режим — «Тестовый», пока вы не проверили лимиты поставщиков
