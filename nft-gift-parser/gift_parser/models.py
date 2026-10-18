"""Модели данных подарка."""
from dataclasses import asdict, dataclass, field

from gift_parser.owner_lang import detect_owner_lang


@dataclass(slots=True)
class Attribute:
    """Атрибут подарка (модель, фон, символ) и его редкость в процентах."""

    name: str
    rarity: float | None = None


@dataclass(slots=True)
class Gift:
    slug: str
    number: int
    url: str
    title: str | None = None
    image: str | None = None
    owner_name: str | None = None
    owner_link: str | None = None
    model: Attribute | None = None
    backdrop: Attribute | None = None
    symbol: Attribute | None = None
    issued: int | None = None
    total: int | None = None
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def owner_lang(self) -> str | None:
        """Язык владельца по письменности имени (ko, ja, zh, ar, ru, …)."""
        return detect_owner_lang(self.owner_name)

    def to_dict(self) -> dict:
        return asdict(self) | {"owner_lang": self.owner_lang}

    def to_flat_dict(self) -> dict:
        """Плоское представление для CSV."""
        row = {
            "slug": self.slug,
            "number": self.number,
            "url": self.url,
            "title": self.title,
            "image": self.image,
            "owner_name": self.owner_name,
            "owner_link": self.owner_link,
            "owner_lang": self.owner_lang,
            "issued": self.issued,
            "total": self.total,
        }
        for key in ("model", "backdrop", "symbol"):
            attr: Attribute | None = getattr(self, key)
            row[key] = attr.name if attr else None
            row[f"{key}_rarity"] = attr.rarity if attr else None
        return row


CSV_FIELDS = [
    "slug", "number", "url", "title",
    "model", "model_rarity", "backdrop", "backdrop_rarity",
    "symbol", "symbol_rarity",
    "owner_name", "owner_link", "owner_lang", "issued", "total", "image",
]
