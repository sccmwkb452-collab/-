"""Official exchange rates of the Bank of Russia (XML_daily.asp, windows-1251)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from ...config import get_settings
from ..http import IntegrationError, check_status, classify, client, with_retries


@dataclass(frozen=True)
class CbrRate:
    code: str
    rate: Decimal  # RUB per 1 unit
    nominal: int
    name: str


@dataclass(frozen=True)
class CbrRates:
    date: datetime
    rates: dict[str, CbrRate]


def parse(xml_bytes: bytes) -> CbrRates:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise IntegrationError(f"ЦБ РФ вернул некорректный XML: {exc}") from exc
    if root.tag != "ValCurs" or "Date" not in root.attrib:
        raise IntegrationError("ЦБ РФ вернул неожиданный формат")
    day = datetime.strptime(root.attrib["Date"], "%d.%m.%Y").replace(tzinfo=UTC)
    rates: dict[str, CbrRate] = {}
    for valute in root.findall("Valute"):
        code = (valute.findtext("CharCode") or "").strip().upper()
        nominal = int(valute.findtext("Nominal") or "1")
        value = Decimal((valute.findtext("Value") or "0").replace(",", "."))
        if not code or value <= 0 or nominal <= 0:
            continue
        rates[code] = CbrRate(code=code, rate=value / nominal, nominal=nominal, name=(valute.findtext("Name") or "").strip())
    if not rates:
        raise IntegrationError("ЦБ РФ не вернул ни одного курса")
    return CbrRates(date=day, rates=rates)


async def fetch() -> CbrRates:
    url = get_settings().cbr_daily_url

    async def call() -> CbrRates:
        try:
            async with client() as c:
                response = await c.get(url)
        except Exception as exc:  # noqa: BLE001
            raise classify(exc) from exc
        check_status(response)
        return parse(response.content)

    return await with_retries(call)
