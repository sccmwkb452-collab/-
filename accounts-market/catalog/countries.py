"""Country names (Russian) and flag emoji for ISO 3166-1 alpha-2 codes."""

from __future__ import annotations

NAMES: dict[str, str] = {
    "RU": "Россия", "US": "США", "GB": "Великобритания", "DE": "Германия", "FR": "Франция", "IT": "Италия",
    "ES": "Испания", "PT": "Португалия", "NL": "Нидерланды", "BE": "Бельгия", "CH": "Швейцария", "AT": "Австрия",
    "PL": "Польша", "CZ": "Чехия", "SK": "Словакия", "HU": "Венгрия", "RO": "Румыния", "BG": "Болгария",
    "GR": "Греция", "SE": "Швеция", "NO": "Норвегия", "FI": "Финляндия", "DK": "Дания", "IE": "Ирландия",
    "EE": "Эстония", "LV": "Латвия", "LT": "Литва", "UA": "Украина", "BY": "Беларусь", "MD": "Молдова",
    "GE": "Грузия", "AM": "Армения", "AZ": "Азербайджан", "KZ": "Казахстан", "UZ": "Узбекистан",
    "KG": "Киргизия", "TJ": "Таджикистан", "TM": "Туркменистан", "TR": "Турция", "IL": "Израиль",
    "AE": "ОАЭ", "SA": "Саудовская Аравия", "QA": "Катар", "EG": "Египет", "MA": "Марокко", "NG": "Нигерия",
    "ZA": "ЮАР", "KE": "Кения", "IN": "Индия", "PK": "Пакистан", "BD": "Бангладеш", "LK": "Шри-Ланка",
    "CN": "Китай", "HK": "Гонконг", "TW": "Тайвань", "JP": "Япония", "KR": "Южная Корея", "VN": "Вьетнам",
    "TH": "Таиланд", "MY": "Малайзия", "SG": "Сингапур", "ID": "Индонезия", "PH": "Филиппины",
    "AU": "Австралия", "NZ": "Новая Зеландия", "CA": "Канада", "MX": "Мексика", "BR": "Бразилия",
    "AR": "Аргентина", "CL": "Чили", "CO": "Колумбия", "PE": "Перу", "VE": "Венесуэла", "CY": "Кипр",
    "RS": "Сербия", "HR": "Хорватия", "SI": "Словения", "ME": "Черногория", "MN": "Монголия",
}

# Search aliases besides the Russian name and the code itself.
ALIASES: dict[str, str] = {
    "usa": "US", "америка": "US", "uk": "GB", "англия": "GB", "britain": "GB", "russia": "RU",
    "germany": "DE", "turkey": "TR", "kazakhstan": "KZ", "emirates": "AE", "эмираты": "AE",
    "philippines": "PH", "india": "IN", "brazil": "BR", "mexico": "MX", "chile": "CL",
    "egypt": "EG", "nigeria": "NG", "bangladesh": "BD", "south africa": "ZA", "korea": "KR", "корея": "KR",
}


def flag(code: str | None) -> str:
    if not code or len(code) != 2 or not code.isalpha():
        return "🏳️"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code.upper())


def name(code: str | None) -> str:
    if not code:
        return "Без страны"
    return NAMES.get(code.upper(), code.upper())


def label(code: str | None) -> str:
    return f"{flag(code)} {name(code)}"


def parse(value: str) -> str | None:
    """'ru', 'RU', 'Россия', 'russia' -> 'RU'. None if unknown."""
    text = value.strip()
    if len(text) == 2 and text.isalpha() and text.upper() in NAMES:
        return text.upper()
    lowered = text.lower()
    for code, ru in NAMES.items():
        if ru.lower() == lowered:
            return code
    return ALIASES.get(lowered)


def search(query: str, codes: list[str]) -> list[str]:
    """Codes from `codes` whose name, code or alias contains the query."""
    q = query.strip().lower()
    if not q:
        return []
    aliases = {code: [a for a, c in ALIASES.items() if c == code] for code in codes}
    result = []
    for code in codes:
        haystack = [code.lower(), name(code).lower(), *aliases[code]]
        if any(q in h for h in haystack):
            result.append(code)
    return result
