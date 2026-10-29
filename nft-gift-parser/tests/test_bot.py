import asyncio

from gift_parser.models import Attribute, Gift

from gift_bot.db import Database
from gift_bot.importer import ImportJob, Target, parse_targets


def gift(number, model, owner="User", slug="PlushPepe"):
    return Gift(slug=slug, number=number, url=f"https://t.me/nft/{slug}-{number}",
                model=Attribute(model, 1.5), backdrop=Attribute("Black"), owner_name=owner)


def test_parse_targets():
    text = (
        "﻿# комментарий\n"
        "https://t.me/nft/PlushPepe-1 t.me/nft/DurovsCap-5\n"
        "PlushPepe-1\n"
        "SnoopDogg 10 1\n"
        "LootBag 3-7\n"
        "SwissWatch\n"
        "\n"
        "@rolls_transfer - https://t.me/nft/VictoryMedal-63230\n"
        "что-то непонятное\n"
    )
    parsed = parse_targets(text)
    assert [(t.slug, t.start, t.end) for t in parsed.targets] == [
        ("PlushPepe", 1, 1), ("DurovsCap", 5, 5), ("SnoopDogg", 1, 10),
        ("LootBag", 3, 7), ("SwissWatch", 1, None), ("VictoryMedal", 63230, 63230),
    ]
    assert parsed.targets[-1].owner == "rolls_transfer"
    assert parsed.targets[0].owner is None
    assert parsed.bad_lines == ["что-то непонятное"]


def test_db_groups_by_model(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    db.save_gifts([gift(1, "Pumpkin"), gift(2, "Pumpkin"), gift(3, "Frog"), gift(1, "Cap", slug="DurovsCap")])
    assert db.collections() == [("DurovsCap", 1), ("PlushPepe", 3)]
    models = db.models("PlushPepe")
    assert [(m.name, m.count) for m in models] == [("Pumpkin", 2), ("Frog", 1)]
    assert [g.number for g in db.gifts_by_model(models[0].id)] == [1, 2]
    assert [g.number for g in db.gifts_by_model(models[0].id, 1, 1)] == [2]

    # Перепарсинг: подарок сменил модель, пустая модель исчезает.
    db.save_gifts([gift(3, "Pumpkin")])
    assert [(m.name, m.count) for m in db.models("PlushPepe")] == [("Pumpkin", 3)]

    db.touch_user(1, "a", "A")
    db.touch_user(2, "b", "B")
    db.set_blocked(2)
    s = db.stats()
    assert (s["users"], s["active"], s["blocked"], s["gifts"], s["models"]) == (2, 1, 1, 4, 2)
    assert db.user_ids() == [1]

    db.add_channel("-100", "Chan", "https://t.me/chan")
    assert [c.title for c in db.channels()] == ["Chan"]
    db.remove_channel("-100")
    assert db.channels() == []


class FakeParser:
    def __init__(self, existing):
        self.existing = existing

    async def get_gift(self, slug, number):
        if slug != "Missing" and number in self.existing:
            g = gift(number, "A" if number % 2 else "B", slug=slug)
            g.total = max(self.existing)
            return g
        return None

    async def get_many(self, refs):
        for slug, n in refs:
            g = await self.get_gift(slug, n)
            if g:
                yield g


def test_import_job(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    job = ImportJob([Target("PlushPepe"), Target("LootBag", 2, 3), Target("Missing")])
    parser = FakeParser(existing={1, 2, 3, 4, 5})

    async def noop(_):
        pass

    asyncio.run(job.run(db, parser, noop))
    assert job.finished and job.found == 7
    assert dict(db.collections()) == {"PlushPepe": 5, "LootBag": 2}
    assert {m.name: m.count for m in db.models("PlushPepe")} == {"A": 3, "B": 2}


def test_import_job_owner_from_file(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    parsed = parse_targets("@dshfrlv - https://t.me/nft/LunarSnake-3\n@x_user - https://t.me/nft/LunarSnake-4\n")

    async def noop(_):
        pass

    # Страницы не нужны: даже если t.me ничего не отдаёт, записи из файла сохраняются.
    job = ImportJob(parsed.targets)
    asyncio.run(job.run(db, FakeParser(existing=set()), noop))
    assert (job.found, job.done, job.total) == (2, 2, 2)
    rows = {g.number: g for g in db.gifts("LunarSnake")}
    assert (rows[3].owner_name, rows[3].owner_link) == ("@dshfrlv", "https://t.me/dshfrlv")

    from gift_bot.user import gift_line
    assert gift_line(3, rows[3]) == '3. @dshfrlv - <a href="https://t.me/nft/LunarSnake-3">Lunar Snake (#3)</a>'


def test_collection_name_and_lists(tmp_path):
    from gift_bot.common import collection_name
    assert [collection_name(x) for x in ("BDayCandle", "UFCStrike", "DurovsCap")] == \
        ["B Day Candle", "UFC Strike", "Durovs Cap"]
    db = Database(str(tmp_path / "t.db"))
    db.save_gifts([gift(1298, "A", slug="LunarSnake"), gift(298, "B", slug="VictoryMedal"),
                   gift(1322, "C", slug="HolidayDrink")])
    assert [g.number for g in db.gifts()] == [298, 1298, 1322]
    assert [g.number for g in db.gifts(None, 1, 1)] == [1298]
    assert db.count_gifts() == 3 and db.count_gifts("LunarSnake") == 1
