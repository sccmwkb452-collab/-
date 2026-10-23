# Развёртывание на Ubuntu VPS

Стек: Docker Compose — `postgres`, `redis`, `migrate` (одноразовый), `api`, `worker`, `bot`, `web` (nginx + статика Mini App и админки), `certbot`.

## 0. Что понадобится

| Что | Где взять |
| --- | --- |
| VPS с Ubuntu 22.04/24.04, 2 vCPU, 2 ГБ RAM, 20 ГБ диска | любой хостинг |
| Домен, например `shop.example.com` | регистратор домена |
| Токен бота | @BotFather → `/newbot` |
| Ваш Telegram ID (для доступа к админке) | @userinfobot |
| (production) ключ платёжного провайдера | см. [PAYMENTS.md](PAYMENTS.md) |
| (production) способ доставки Stars | см. [DELIVERY.md](DELIVERY.md) |

## 1. Домен

В DNS создайте **A-запись** `shop.example.com → IP сервера` (и AAAA, если у сервера есть IPv6). Проверка:

```bash
dig +short shop.example.com
```

Порты 80 и 443 должны быть открыты (скрипт установки открывает их в `ufw`, если он включён; у облачных провайдеров проверьте ещё и firewall в панели).

## 2. Установка

```bash
sudo apt-get update && sudo apt-get install -y git
sudo git clone <URL репозитория> /opt/starshop
cd /opt/starshop/stars-shop
sudo ./deploy/scripts/install.sh      # 1-й запуск: ставит Docker и создаёт .env со случайными секретами
sudo nano .env                         # DOMAIN, LETSENCRYPT_EMAIL, BOT_TOKEN, BOT_USERNAME, ADMIN_TELEGRAM_IDS
sudo ./deploy/scripts/install.sh      # 2-й запуск: сборка, запуск, HTTPS, ежедневный бэкап
```

Скрипт:
1. ставит Docker Engine и включает автозапуск (`systemctl enable docker`) — после перезагрузки сервера все контейнеры поднимутся сами (`restart: unless-stopped`);
2. включает ротацию логов Docker (`/etc/docker/daemon.json`, 5 × 10 МБ на контейнер);
3. генерирует `SECRET_KEY`, пароль БД и `BOT_WEBHOOK_SECRET`; `.env` получает права `600`;
4. собирает образы, применяет миграции, создаёт стартовый DEMO-каталог (только если каталог пуст);
5. выпускает сертификат Let's Encrypt (`init-letsencrypt.sh`) и переключает nginx на HTTPS;
6. добавляет в cron ежедневный бэкап БД в 03:17.

## 3. HTTPS

Пока сертификата нет, nginx работает только по HTTP (этого достаточно для проверки Let's Encrypt). `deploy/scripts/init-letsencrypt.sh` получает сертификат через webroot и перезапускает `web` — после этого HTTP перенаправляется на HTTPS, включены HSTS и HTTP/2.

Продление автоматическое: контейнер `certbot` раз в 12 часов вызывает `certbot renew`, nginx перечитывает сертификаты каждые 6 часов.

Для пробных запусков используйте тестовый центр сертификации (без лимитов): `LETSENCRYPT_STAGING=1 ./deploy/scripts/init-letsencrypt.sh`.

## 4. Настройка бота в @BotFather

1. **Mini App:** `/mybots` → бот → *Bot Settings* → *Menu Button* → URL `https://shop.example.com/`. Бот при старте сам ставит кнопку меню «Магазин», если `PUBLIC_BASE_URL` использует HTTPS.
2. **Ссылки вида `t.me/<bot>/<app>`** (необязательно): `/newapp` → укажите тот же URL и короткое имя → впишите его в `WEBAPP_SHORT_NAME`.
3. **Вход в админку через Telegram Login Widget** (необязательно): `/setdomain` → `shop.example.com`. Основной способ входа — команда `/admin` в боте, для неё ничего настраивать не нужно.
4. **Режим webhook** (необязательно): `BOT_MODE=webhook` в `.env` → `docker compose up -d bot`. Бот сам зарегистрирует `https://DOMAIN/tg/webhook` с секретным заголовком.

## 5. Первый вход в админку

Напишите боту `/admin` с аккаунта из `ADMIN_TELEGRAM_IDS` и нажмите «Войти в админ-панель». Ссылка одноразовая и действует 5 минут. Без бота ссылку можно получить на сервере:

```bash
docker compose exec api python -m starshop.cli admin-link <telegram_id>
```

## 6. Переход в PRODUCTION

1. Подключите платёжного провайдера ([PAYMENTS.md](PAYMENTS.md)) и способ доставки ([DELIVERY.md](DELIVERY.md)).
2. Задайте в админке реальные цены и себестоимость (*Каталог*).
3. Проведите тестовую покупку на тестовой сети провайдера (`CRYPTOPAY_NETWORK=testnet`).
4. Установите в `.env` `ALLOW_PRODUCTION=true`, выполните `docker compose up -d`.
5. В админке: *Настройки → Магазин → Режим работы → PRODUCTION*. Переключение отклоняется, если не настроены реальная оплата или доставка.

## 7. Обновление

```bash
cd /opt/starshop/stars-shop
sudo ./deploy/scripts/update.sh
```

Порядок: бэкап (`pre-update`) → `git pull --ff-only` → сборка образов → миграции → перезапуск → ожидание `healthy` → краткая диагностика.

Только миграции: `./deploy/scripts/migrate.sh`.

## 8. Резервные копии

* Автоматически: ежедневно в 03:17 (cron) в `stars-shop/backups/`, хранится 14 дней (`BACKUP_KEEP_DAYS`).
* Вручную: `./deploy/scripts/backup.sh`.
* Копия вне сервера: установите `rclone`, задайте `BACKUP_RCLONE_REMOTE=remote:bucket/path` в окружении cron. Держите хотя бы одну копию вне VPS.

## 9. Восстановление после сбоя

| Ситуация | Действия |
| --- | --- |
| Упал один контейнер | Docker перезапускает его сам. Проверьте `./deploy/scripts/diagnose.sh` и `docker compose logs <service>` |
| Сервер перезагрузился | Ничего делать не нужно: Docker и контейнеры стартуют автоматически |
| Повреждена БД / ошибочные данные | `./deploy/scripts/restore.sh backups/starshop-<дата>.dump` — перед восстановлением делается страховочная копия `pre-restore` |
| Сервер утерян | Новый VPS → шаги 2–3 с прежним `.env` → `restore.sh` с копией из внешнего хранилища → обновите A-запись домена |
| Сертификат не выпускается | Проверьте DNS и доступность порта 80, затем повторите `init-letsencrypt.sh` |
| Неясный статус доставки | В админке у заказа будет статус «Нужен оператор». Проверьте у поставщика и нажмите «Подтвердить доставку» (с номером транзакции) или «Повторить доставку» |

Незавершённые операции после аварии восстанавливаются сами: воркер повторно опрашивает провайдера по ожидающим платежам, возвращает в очередь зависшие задачи доставки (если поставщик защищён от повторов) и продолжает отправку уведомлений.

## 10. Диагностика

```bash
./deploy/scripts/diagnose.sh          # статус контейнеров, health, конфигурация без секретов,
                                      # срок сертификата, webhook бота, свободное место, последние ошибки
docker compose logs -f api worker bot # JSON-логи; секреты в них маскируются
docker compose ps                     # health-статусы
```

Health-эндпоинты: `GET /api/health` (живость), `GET /api/health/ready` (БД + Redis), воркер пишет heartbeat-файл (проверяется в healthcheck), nginx — `/nginx-health`.
