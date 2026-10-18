# NFT Gift Parser

Простой парсер NFT-подарков Telegram. Читает публичные страницы
`https://t.me/nft/<Коллекция>-<номер>`. API-ключи, аккаунт и Telethon не нужны.

С каждой страницы берёт:

- название и картинку подарка;
- модель, фон и символ вместе с редкостью (в %);
- владельца (имя и ссылку, если профиль публичный);
- сколько выпущено и сколько всего в коллекции.

## Установка

```bash
cd nft-gift-parser
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Использование

```bash
# Один подарок (ссылку можно писать полностью или коротко)
python -m gift_parser https://t.me/nft/PlushPepe-1
python -m gift_parser PlushPepe-1 DurovsCap-42

# Диапазон номеров -> CSV
python -m gift_parser PlushPepe --from 1 --to 200 -o pepe.csv

# Вся коллекция (размер берётся со страницы первого подарка) -> JSON
python -m gift_parser PlushPepe -o pepe.json

# Фильтры: модель/фон/символ (подстрока) и редкость
python -m gift_parser PlushPepe --to 500 --model Pumpkin
python -m gift_parser PlushPepe --max-rarity 0.5 -o rare.csv
```

| Флаг | Значение |
|------|----------|
| `--from` / `--to` | диапазон номеров (по умолчанию от 1 до конца коллекции) |
| `-o file.csv` / `-o file.json` | формат выбирается по расширению файла |
| `--format table\|json\|csv` | формат вывода в консоль |
| `-c 5` | сколько запросов идёт параллельно |
| `--delay 0.2` | пауза после каждого запроса, в секундах |
| `--proxy http://host:port` | HTTP-прокси |
| `--lang ru` | язык страниц (поддерживаются en и ru) |

На ответ 429 парсер ждёт `Retry-After` и повторяет запрос. Сетевые ошибки
повторяются до 3 раз. Несуществующие номера пропускаются.

## Telegram-бот

```bash
BOT_TOKEN=123456:ABC... python bot.py
```

В чате с ботом:

- `PlushPepe-1` или `https://t.me/nft/PlushPepe-1` — карточка подарка с картинкой;
- `PlushPepe 1 100` — CSV-файл с номерами 1–100 (до 500 за раз).

## Использование из кода

```python
import asyncio
from gift_parser import GiftParser

async def main():
    async with GiftParser(concurrency=5) as p:
        gift = await p.get_gift("PlushPepe", 1)
        print(gift.model, gift.owner_name)
        async for g in p.get_collection("PlushPepe", 1, 100):
            print(g.number, g.backdrop)

asyncio.run(main())
```

## Тесты

```bash
pip install pytest
python -m pytest -q
```
