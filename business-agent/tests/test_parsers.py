from pathlib import Path

from sqlalchemy import select

from app.db.models import Contact, OutreachTask, ParserConfig
from app.nft.pages import parse_gift_html
from app.parsers.file_import import FileImportAdapter, parse_import_file
from app.parsers.nft_owners import NftOwnersAdapter
from app.parsers.pipeline import run_parser
from app.parsers.registry import detect_source

FIX = Path(__file__).parent / "fixtures"
CSV = """user_id;username;name;role;text;price;currency;city;model
101;@alice;Alice;seller;Продаю Plush Pepe;12;TON;Москва;Pumpkin
102;bob;Bob;buyer;Куплю подарки;;;Москва;
103;carol;Carol;продавец;Продаю шапку Durov;50;TON;Казань;Cap
101;alice;Alice dup;seller;Продаю Plush Pepe;12;TON;Москва;Pumpkin
;;NoContact;seller;Продаю;5;TON;Москва;
104;dave;Dave;seller;Продаю Pepe;99;TON;Москва;Pumpkin
"""


def test_detect_source():
    assert detect_source("https://t.me/nft/PlushPepe-1").adapter == "nft_owners"
    assert detect_source("https://parser.example.com/api").adapter == "http_api"
    bot = detect_source("@some_parser_bot")
    assert bot.adapter == "file_import" and "Bot API" in bot.explanation
    assert detect_source("@durov").adapter is None


def test_parse_csv_and_normalize():
    rows = parse_import_file(CSV.encode(), "export.csv")
    assert len(rows) == 6
    cand = FileImportAdapter.__new__(FileImportAdapter).normalize_result(rows[0])
    assert cand.telegram_user_id == 101 and cand.username == "alice" and cand.role == "seller"
    assert cand.attributes == {"model": "Pumpkin"} and str(cand.price) == "12"


async def test_pipeline_filters_dedups_and_limits(sessions, owner):
    async with sessions() as s:
        cfg = ParserConfig(owner_id=owner.id, name="imp", adapter="file_import", target_role="seller",
                           keywords=["продаю"], filters={"model": "pump"}, geo="москва",
                           ranges={"price": {"min": "1", "max": "50"}}, daily_contact_limit=10, total_contact_limit=10,
                           stop_rules={"max_results": 100}, import_rows=parse_import_file(CSV.encode(), "x.csv"))
        s.add(cfg)
        opted = Contact(owner_id=owner.id, telegram_user_id=999, username="ghost", opted_out=True, profile={})
        s.add(opted)
        await s.flush()
        report = await run_parser(s, owner, cfg, FileImportAdapter(cfg))
        await s.commit()
        assert report.queued == 1, report.render()
        assert report.rejected.get("дубликат в выдаче") == 1
        assert report.rejected.get("не нормализован") == 1  # нет ни ID, ни username
        assert report.rejected.get("вне диапазона price") == 1
        tasks = (await s.scalars(select(OutreachTask))).all()
        assert len(tasks) == 1 and tasks[0].status == "pending_approval"
        # Повторный запуск не создаёт дублей.
        again = await run_parser(s, owner, cfg, FileImportAdapter(cfg))
        assert again.queued == 0


async def test_pipeline_respects_opt_out(sessions, owner):
    rows = [{"user_id": "201", "username": "eve", "role": "seller", "text": "Продаю"}]
    async with sessions() as s:
        s.add(Contact(owner_id=owner.id, telegram_user_id=201, username="eve", opted_out=True, profile={}))
        cfg = ParserConfig(owner_id=owner.id, name="imp2", adapter="file_import", import_rows=rows, keywords=[],
                           filters={}, ranges={}, stop_rules={})
        s.add(cfg)
        await s.flush()
        report = await run_parser(s, owner, cfg, FileImportAdapter(cfg))
        assert report.queued == 0 and report.rejected == {"отказался от общения": 1}


async def test_pipeline_daily_limit_stops(sessions, owner):
    rows = [{"user_id": str(300 + i), "role": "seller"} for i in range(5)]
    async with sessions() as s:
        cfg = ParserConfig(owner_id=owner.id, name="imp3", adapter="file_import", import_rows=rows, keywords=[],
                           filters={}, ranges={}, stop_rules={}, daily_contact_limit=2, total_contact_limit=100)
        s.add(cfg)
        await s.flush()
        report = await run_parser(s, owner, cfg, FileImportAdapter(cfg))
        assert report.queued == 2 and report.stopped_by == "дневной лимит парсера"


class FakeGiftClient:
    async def get(self, slug, number):
        html = (FIX / "gift.html").read_text() if number == 7 else (FIX / "missing.html").read_text()
        return parse_gift_html(html, slug, number)

    async def close(self):
        pass


async def test_nft_owner_adapter(sessions, owner):
    async with sessions() as s:
        cfg = ParserConfig(owner_id=owner.id, name="nft", adapter="nft_owners", resource="https://t.me/nft/PlushPepe-1",
                           keywords=[], filters={"backdrop": "black"}, ranges={"number": {"min": "5", "max": "8"},
                                                                                 "model_rarity_percent": {"max": "1"}},
                           stop_rules={"max_results": 10})
        s.add(cfg)
        await s.flush()
        adapter = NftOwnersAdapter(cfg, client=FakeGiftClient())
        adapter.validate = lambda: _ok()
        report = await run_parser(s, owner, cfg, adapter)
        assert report.queued == 1, report.render()
        contact = await s.scalar(select(Contact).where(Contact.username == "someuser"))
        assert contact.profile["attributes"]["model"] == "Pumpkin Pepe"


async def _ok():
    return True, "ok"
