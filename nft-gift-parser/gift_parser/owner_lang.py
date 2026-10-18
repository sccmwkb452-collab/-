"""Определение языка владельца по письменности его имени.

Telegram не сообщает страну владельца, поэтому смотрим, какими буквами
написано имя: хангыль → корейский, кана → японский, иероглифы → китайский,
арабская вязь → арабский, кириллица → русский и т.д. Латиница и эмодзи
ничего не говорят о языке — для них возвращается "latin" или None.
"""
import re

# (код, регулярка по диапазону Unicode). Порядок важен: кана проверяется раньше
# иероглифов, потому что японские имена часто смешивают кандзи и кану.
_SCRIPTS = [
    ("ko", re.compile(r"[ᄀ-ᇿ㄰-㆏가-힯]")),
    ("ja", re.compile(r"[぀-ゟ゠-ヿㇰ-ㇿｦ-ﾟ]")),
    ("zh", re.compile(r"[㐀-䶿一-鿿豈-﫿]")),
    ("ar", re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")),
    ("he", re.compile(r"[֐-׿]")),
    ("th", re.compile(r"[฀-๿]")),
    ("hi", re.compile(r"[ऀ-ॿ]")),
    ("ru", re.compile(r"[Ѐ-ӿ]")),
    ("latin", re.compile(r"[A-Za-zÀ-ɏ]")),
]
_UKRAINIAN = re.compile(r"[ієїґІЄЇҐ]")

OWNER_LANGS = {
    "ko": "🇰🇷 корейский", "ja": "🇯🇵 японский", "zh": "🇨🇳 китайский", "ar": "🇸🇦 арабский",
    "he": "🇮🇱 иврит", "th": "🇹🇭 тайский", "hi": "🇮🇳 хинди", "ru": "🇷🇺 русский",
    "uk": "🇺🇦 украинский", "latin": "🔤 латиница",
}


def detect_owner_lang(name: str | None) -> str | None:
    """Язык по письменности имени: 'ko', 'ja', 'zh', 'ar', 'ru', … или None."""
    if not name:
        return None
    for code, rx in _SCRIPTS:
        if rx.search(name):
            if code == "ru" and _UKRAINIAN.search(name):
                return "uk"
            return code
    return None
