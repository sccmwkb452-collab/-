"""Тексты бота на разных языках. Добавить язык — скопировать блок "en" и перевести."""

DEFAULT = "ru"

TEXTS: dict[str, dict[str, str]] = {
    "ru": {
        "start": "Пришли ссылку на NFT-подарок, например <code>https://t.me/nft/PlushPepe-1</code> "
                 "или <code>PlushPepe-1</code>.\n\n"
                 "Диапазон в CSV: <code>PlushPepe 1 100</code> (до {max} шт. за раз).\n"
                 "Новые коллекции: /gifts, язык: /lang",
        "model": "Модель", "backdrop": "Фон", "symbol": "Символ", "owner": "Владелец", "issued": "Выпущено",
        "no_collection": "Такой коллекции нет в списке.",
        "found": "Найдено", "latest": "Самые новые коллекции",
        "lang_now": "Сейчас: {lang}. Пример: <code>/lang ja</code>",
        "lang_set": "Язык: {lang}",
        "too_big": "Слишком большой диапазон, максимум {max}.",
        "parsing": "⏳ Парсю {slug} #{start}–{end}…",
        "nothing": "Ничего не найдено. Проверь название коллекции (/gifts).",
        "found_of": "Найдено {n} из {total}",
        "not_understood": "Не понял. Пример: <code>PlushPepe-1</code> или <code>PlushPepe 1 100</code>",
        "not_found": "Подарок не найден.",
    },
    "en": {
        "start": "Send a link to an NFT gift, e.g. <code>https://t.me/nft/PlushPepe-1</code> "
                 "or <code>PlushPepe-1</code>.\n\n"
                 "Range as CSV: <code>PlushPepe 1 100</code> (up to {max} at a time).\n"
                 "New collections: /gifts, language: /lang",
        "model": "Model", "backdrop": "Backdrop", "symbol": "Symbol", "owner": "Owner", "issued": "Issued",
        "no_collection": "This collection is not in the list.",
        "found": "Found", "latest": "Newest collections",
        "lang_now": "Current: {lang}. Example: <code>/lang ja</code>",
        "lang_set": "Language: {lang}",
        "too_big": "Range is too large, maximum is {max}.",
        "parsing": "⏳ Parsing {slug} #{start}–{end}…",
        "nothing": "Nothing found. Check the collection name (/gifts).",
        "found_of": "Found {n} of {total}",
        "not_understood": "I didn't get that. Example: <code>PlushPepe-1</code> or <code>PlushPepe 1 100</code>",
        "not_found": "Gift not found.",
    },
    "ja": {
        "start": "NFTギフトのリンクを送ってください。例: <code>https://t.me/nft/PlushPepe-1</code> "
                 "または <code>PlushPepe-1</code>\n\n"
                 "範囲をCSVで取得: <code>PlushPepe 1 100</code>（一度に最大{max}件）\n"
                 "新しいコレクション: /gifts、言語: /lang",
        "model": "モデル", "backdrop": "背景", "symbol": "シンボル", "owner": "所有者", "issued": "発行数",
        "no_collection": "このコレクションはリストにありません。",
        "found": "見つかりました", "latest": "最新のコレクション",
        "lang_now": "現在の言語: {lang}。例: <code>/lang ko</code>",
        "lang_set": "言語: {lang}",
        "too_big": "範囲が大きすぎます。最大{max}件です。",
        "parsing": "⏳ {slug} #{start}–{end} を取得中…",
        "nothing": "見つかりませんでした。コレクション名を確認してください（/gifts）。",
        "found_of": "{total}件中{n}件が見つかりました",
        "not_understood": "理解できませんでした。例: <code>PlushPepe-1</code> または <code>PlushPepe 1 100</code>",
        "not_found": "ギフトが見つかりません。",
    },
    "ko": {
        "start": "NFT 선물 링크를 보내주세요. 예: <code>https://t.me/nft/PlushPepe-1</code> "
                 "또는 <code>PlushPepe-1</code>\n\n"
                 "범위를 CSV로 받기: <code>PlushPepe 1 100</code> (한 번에 최대 {max}개)\n"
                 "새 컬렉션: /gifts, 언어: /lang",
        "model": "모델", "backdrop": "배경", "symbol": "심볼", "owner": "소유자", "issued": "발행",
        "no_collection": "목록에 없는 컬렉션입니다.",
        "found": "검색 결과", "latest": "최신 컬렉션",
        "lang_now": "현재 언어: {lang}. 예: <code>/lang ja</code>",
        "lang_set": "언어: {lang}",
        "too_big": "범위가 너무 큽니다. 최대 {max}개입니다.",
        "parsing": "⏳ {slug} #{start}–{end} 가져오는 중…",
        "nothing": "찾을 수 없습니다. 컬렉션 이름을 확인하세요 (/gifts).",
        "found_of": "{total}개 중 {n}개 찾음",
        "not_understood": "이해하지 못했습니다. 예: <code>PlushPepe-1</code> 또는 <code>PlushPepe 1 100</code>",
        "not_found": "선물을 찾을 수 없습니다.",
    },
    "zh": {
        "start": "发送 NFT 礼物链接，例如 <code>https://t.me/nft/PlushPepe-1</code> "
                 "或 <code>PlushPepe-1</code>。\n\n"
                 "按范围导出 CSV：<code>PlushPepe 1 100</code>（每次最多 {max} 个）\n"
                 "最新系列：/gifts，语言：/lang",
        "model": "模型", "backdrop": "背景", "symbol": "图案", "owner": "拥有者", "issued": "已发行",
        "no_collection": "列表中没有这个系列。",
        "found": "找到", "latest": "最新系列",
        "lang_now": "当前语言：{lang}。例如：<code>/lang ja</code>",
        "lang_set": "语言：{lang}",
        "too_big": "范围太大，最多 {max} 个。",
        "parsing": "⏳ 正在获取 {slug} #{start}–{end}…",
        "nothing": "未找到。请检查系列名称（/gifts）。",
        "found_of": "共 {total} 个，找到 {n} 个",
        "not_understood": "无法识别。例如：<code>PlushPepe-1</code> 或 <code>PlushPepe 1 100</code>",
        "not_found": "未找到礼物。",
    },
    "ar": {
        "start": "أرسل رابط هدية NFT، مثل <code>https://t.me/nft/PlushPepe-1</code> "
                 "أو <code>PlushPepe-1</code>.\n\n"
                 "نطاق كملف CSV: <code>PlushPepe 1 100</code> (حتى {max} في المرة).\n"
                 "أحدث المجموعات: /gifts، اللغة: /lang",
        "model": "النموذج", "backdrop": "الخلفية", "symbol": "الرمز", "owner": "المالك", "issued": "تم الإصدار",
        "no_collection": "هذه المجموعة غير موجودة في القائمة.",
        "found": "النتائج", "latest": "أحدث المجموعات",
        "lang_now": "اللغة الحالية: {lang}. مثال: <code>/lang ja</code>",
        "lang_set": "اللغة: {lang}",
        "too_big": "النطاق كبير جدًا، الحد الأقصى {max}.",
        "parsing": "⏳ جارٍ جلب {slug} #{start}–{end}…",
        "nothing": "لم يتم العثور على شيء. تحقق من اسم المجموعة (/gifts).",
        "found_of": "تم العثور على {n} من {total}",
        "not_understood": "لم أفهم. مثال: <code>PlushPepe-1</code> أو <code>PlushPepe 1 100</code>",
        "not_found": "لم يتم العثور على الهدية.",
    },
}


def t(lang: str, key: str, **kw) -> str:
    """Текст на языке `lang`; если перевода нет — на английском."""
    text = TEXTS.get(lang, TEXTS["en"]).get(key) or TEXTS["en"][key]
    return text.format(**kw) if kw else text
