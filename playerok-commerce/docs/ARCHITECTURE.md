# Архитектура

```
                 ┌─────────────── Vercel ───────────────┐
 браузер ──────► │ Next.js панель   /api/* → BACKEND_URL │
                 └───────────────────┬──────────────────┘
                                     │ HTTPS
                 ┌─────────── VPS ───▼──────────────────────────────────────────┐
 Telegram ◄────► │ bot (aiogram, polling) ─┐                                     │
                 │                          │                                     │
                 │ Caddy ─► api (FastAPI) ──┼──► PostgreSQL ◄── worker            │
                 │                          │    (данные, очередь задач,          │
                 │ redis (состояние диалогов бота)  уведомления, журнал)         │
                 └──────────────────────────┴─────────────────────────────────────┘
                     worker ──► поставщики (Fragment, VexBoost, Reloadly), ЦБ РФ, Telegram Bot API
```

| Компонент | Код | Роль |
| --- | --- | --- |
| API | `backend/autocommerce/api` | REST для панели: сессии, CSRF, роли, валидация, единый формат ошибок |
| Бот | `backend/autocommerce/bot` | 16 разделов меню, ввод заказов и сообщений, подтверждения, уведомления с кнопками |
| Воркер | `backend/autocommerce/worker` | Очередь задач: обработка заказов, закупки, синхронизация, пересчёт цен, отчёты, отправка уведомлений |
| Сервисы | `backend/autocommerce/services` | Вся бизнес-логика; API, бот и воркер — тонкие слои поверх неё |
| Интеграции | `backend/autocommerce/integrations` | Адаптеры поставщиков, PlayerOK (ручной режим), ЦБ РФ; общий HTTP-клиент с повторами только для чтения |
| Изображения | `backend/autocommerce/imaging` | Генератор по шаблонам (Pillow) — см. [IMAGES.md](IMAGES.md) |
| Панель | `web/` | Next.js 16, App Router, Tailwind 4, Radix, Recharts |

## Данные

PostgreSQL, SQLAlchemy 2 (async), миграции Alembic (`backend/migrations`). Деньги — `NUMERIC(14,2)`, курсы — `NUMERIC(18,6)`, проценты — `NUMERIC(9,4)`; в коде только `Decimal`, `float` для денег запрещён. Перечисления — `VARCHAR` + `CHECK`.

Основные таблицы: `products`, `product_categories` (комиссия PlayerOK, допустимость), `inventory`, `digital_codes`, `suppliers`, `supplier_products`, `supplier_price_history`, `supplier_orders`, `fx_rates`, `market_price_snapshots`, `price_rules`, `research_scores`, `listings`, `listing_revisions`, `listing_images`, `image_templates`, `orders`, `order_items`, `order_events`, `transactions`, `customer_messages`, `reviews`, `autoresponder_rules`, `auto_settings`, `automation_jobs`, `automation_logs`, `notifications`, `sync_runs`, `audit_logs`, `users`, `roles`, `web_sessions`, `heartbeats`, `settings`, `integration_credentials`.

## Надёжность

**Очередь задач в PostgreSQL** (`automation_jobs`): выбор `FOR UPDATE SKIP LOCKED`, аренда с продлением, восстановление «зависших» задач, экспоненциальная задержка повторов, частичный уникальный индекс по `dedupe_key` — одна и та же задача не ставится дважды. Периодические задачи (курсы, синхронизация поставщиков, пересчёт цен, исследование, автовыставление, очистка) ставятся по временным слотам: перезапуск или второй воркер не создают дублей.

**Уведомления — transactional outbox**: запись уведомления делается в той же транзакции, что и событие; воркер отправляет их в Telegram, соблюдая `retry_after` при 429, тихие часы и выключенные виды.

**Заказы**:

- `uq_orders_marketplace_external` — одна сделка PlayerOK = один заказ (`INSERT … ON CONFLICT`);
- переходы статусов только по таблице допустимых, каждый переход — запись в `order_events`;
- оптимистичная блокировка (`version`) + `SELECT … FOR UPDATE` при изменении;
- закупка: строка `supplier_orders` с уникальным `idempotency_key` фиксируется до вызова поставщика; тайм-аут → `unknown`, сверка по ключу (Reloadly `customIdentifier`), автоматического повтора нет;
- коды: резерв `FOR UPDATE SKIP LOCKED`, проверка «выданный код привязан к заказу» на уровне `CHECK`, уникальный HMAC-отпечаток кода;
- транзакции (выручка, комиссии, закупка) идемпотентны по `dedupe_key`.

**Один экземпляр бота**: advisory lock PostgreSQL.

**Здоровье**: воркер и бот пишут сигнал каждые 30 секунд; `/api/v1/health/ready` и `python -m autocommerce.cli health <db|worker|bot>` используются в healthcheck контейнеров.

## Цены (Pricing Engine)

`backend/autocommerce/services/pricing.py`, только `Decimal`:

```
C  = закупка + комиссия поставщика + конвертация валюты + прочие расходы       (полная себестоимость)
r  = mp + pay + reserve + (1 − mp) · withdrawal                                (доля расходов от цены)
NetProfit(P) = P − C − P·r
MinPrice = max( (C + πmin)/(1 − r),  C/(1 − r − m),  C·(1 + k)/(1 − r) )        → округление вверх до шага
```

`mp` — комиссия PlayerOK категории, `pay` — платёжная комиссия, `reserve` — резерв на возвраты, `withdrawal` — комиссия вывода (берётся с суммы после комиссии площадки), `πmin` — минимальная прибыль, `m` — минимальная маржа, `k` — минимальный ROI. Целевая цена строится так же по целевым порогам; конкурентная — ниже минимальной цены конкурента на `undercut`, но не ниже минимальной и не дальше `max_discount` от целевой. Правила: глобальные → категория → товар.

## Тестовый режим

`APP_MODE=test`: адаптеры поставщиков не вызывают методы покупки — результат имитируется (`TEST-…`), публикации не выполняются, все тестовые записи помечены `is_test` и исключены из аналитики. Боевой режим требует `ALLOW_LIVE_OPERATIONS=true` и переключателя владельца.

## Тесты

`backend/tests` — 96 тестов на настоящем PostgreSQL (`pac_test`): цены и пограничные случаи, идемпотентность заказов и закупок, конкурентная выдача кодов, адаптеры поставщиков на записанных ответах, API (сессии, CSRF, роли, экспорт), бот (каждый раздел меню), генератор изображений.

```bash
cd backend
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
cd ../web && npm run typecheck && npm run lint && npm run build
```
