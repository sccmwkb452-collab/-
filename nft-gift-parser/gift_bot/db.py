"""SQLite-база: пользователи, подарки, модели и каналы обязательной подписки."""
import sqlite3
import time
from dataclasses import dataclass

from gift_parser.models import Gift

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY,
    username   TEXT,
    first_name TEXT,
    joined_at  INTEGER NOT NULL,
    blocked    INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS models (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    UNIQUE (slug, name)
);
CREATE TABLE IF NOT EXISTS gifts (
    slug            TEXT NOT NULL,
    number          INTEGER NOT NULL,
    title           TEXT,
    image           TEXT,
    model_id        INTEGER REFERENCES models(id),
    model_rarity    REAL,
    backdrop        TEXT,
    backdrop_rarity REAL,
    symbol          TEXT,
    symbol_rarity   REAL,
    owner_name      TEXT,
    owner_link      TEXT,
    updated_at      INTEGER NOT NULL,
    PRIMARY KEY (slug, number)
);
CREATE INDEX IF NOT EXISTS gifts_model ON gifts (model_id, number);
CREATE TABLE IF NOT EXISTS channels (
    chat_id TEXT PRIMARY KEY,
    title   TEXT NOT NULL,
    url     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

NO_MODEL = "Без модели"
DAY = 86400


@dataclass(slots=True)
class ModelRow:
    id: int
    slug: str
    name: str
    count: int


@dataclass(slots=True)
class GiftRow:
    slug: str
    number: int
    title: str | None
    owner_name: str | None
    owner_link: str | None
    backdrop: str | None
    symbol: str | None
    model_rarity: float | None

    @property
    def url(self) -> str:
        return f"https://t.me/nft/{self.slug}-{self.number}"


@dataclass(slots=True)
class Channel:
    chat_id: str
    title: str
    url: str


class Database:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # --- пользователи ---

    def touch_user(self, user_id: int, username: str | None, first_name: str | None) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO users (id, username, first_name, joined_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET username=excluded.username, "
                "first_name=excluded.first_name, blocked=0",
                (user_id, username, first_name, int(time.time())),
            )

    def set_blocked(self, user_id: int) -> None:
        with self.conn:
            self.conn.execute("UPDATE users SET blocked=1 WHERE id=?", (user_id,))

    def user_ids(self) -> list[int]:
        return [r[0] for r in self.conn.execute("SELECT id FROM users WHERE blocked=0")]

    # --- подарки ---

    def _model_id(self, slug: str, name: str) -> int:
        self.conn.execute("INSERT OR IGNORE INTO models (slug, name) VALUES (?, ?)", (slug, name))
        return self.conn.execute(
            "SELECT id FROM models WHERE slug=? AND name=?", (slug, name)
        ).fetchone()[0]

    def save_gifts(self, gifts: list[Gift]) -> None:
        now = int(time.time())
        with self.conn:
            for g in gifts:
                model_id = self._model_id(g.slug, g.model.name if g.model else NO_MODEL)
                self.conn.execute(
                    "INSERT OR REPLACE INTO gifts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        g.slug, g.number, g.title, g.image, model_id,
                        g.model.rarity if g.model else None,
                        g.backdrop.name if g.backdrop else None,
                        g.backdrop.rarity if g.backdrop else None,
                        g.symbol.name if g.symbol else None,
                        g.symbol.rarity if g.symbol else None,
                        g.owner_name, g.owner_link, now,
                    ),
                )
            # Модели, у которых не осталось подарков (подарок сменил модель при перепарсинге).
            self.conn.execute(
                "DELETE FROM models WHERE id NOT IN (SELECT DISTINCT model_id FROM gifts)"
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO meta VALUES ('last_upload', ?)", (str(now),)
            )

    def clear_gifts(self) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM gifts")
            self.conn.execute("DELETE FROM models")

    def collections(self) -> list[tuple[str, int]]:
        return self.conn.execute(
            "SELECT slug, COUNT(*) FROM gifts GROUP BY slug ORDER BY slug"
        ).fetchall()

    def models(self, slug: str) -> list[ModelRow]:
        rows = self.conn.execute(
            "SELECT m.id, m.slug, m.name, COUNT(*) AS c FROM models m "
            "JOIN gifts g ON g.model_id = m.id WHERE m.slug=? "
            "GROUP BY m.id ORDER BY c DESC, m.name",
            (slug,),
        )
        return [ModelRow(*r) for r in rows]

    def model(self, model_id: int) -> ModelRow | None:
        r = self.conn.execute(
            "SELECT m.id, m.slug, m.name, COUNT(g.number) FROM models m "
            "LEFT JOIN gifts g ON g.model_id = m.id WHERE m.id=? GROUP BY m.id",
            (model_id,),
        ).fetchone()
        return ModelRow(*r) if r else None

    def gifts_by_model(self, model_id: int, offset: int = 0, limit: int | None = None) -> list[GiftRow]:
        rows = self.conn.execute(
            "SELECT slug, number, title, owner_name, owner_link, backdrop, symbol, model_rarity "
            "FROM gifts WHERE model_id=? ORDER BY number LIMIT ? OFFSET ?",
            (model_id, -1 if limit is None else limit, offset),
        )
        return [GiftRow(*r) for r in rows]

    # --- обязательная подписка ---

    def channels(self) -> list[Channel]:
        return [Channel(*r) for r in self.conn.execute("SELECT chat_id, title, url FROM channels")]

    def add_channel(self, chat_id: str, title: str, url: str) -> None:
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO channels VALUES (?, ?, ?)", (chat_id, title, url))

    def remove_channel(self, chat_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM channels WHERE chat_id=?", (chat_id,))

    # --- статистика ---

    def stats(self) -> dict[str, int | None]:
        now = int(time.time())
        q = lambda sql, *a: self.conn.execute(sql, a).fetchone()[0]  # noqa: E731
        last = self.conn.execute("SELECT value FROM meta WHERE key='last_upload'").fetchone()
        return {
            "users": q("SELECT COUNT(*) FROM users"),
            "active": q("SELECT COUNT(*) FROM users WHERE blocked=0"),
            "blocked": q("SELECT COUNT(*) FROM users WHERE blocked=1"),
            "today": q("SELECT COUNT(*) FROM users WHERE joined_at>=?", now - DAY),
            "week": q("SELECT COUNT(*) FROM users WHERE joined_at>=?", now - 7 * DAY),
            "gifts": q("SELECT COUNT(*) FROM gifts"),
            "collections": q("SELECT COUNT(DISTINCT slug) FROM gifts"),
            "models": q("SELECT COUNT(*) FROM models"),
            "channels": q("SELECT COUNT(*) FROM channels"),
            "last_upload": int(last[0]) if last else None,
        }
