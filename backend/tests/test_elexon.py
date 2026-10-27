import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from app.elexon import ElexonClient, parse_actuals, parse_forecasts

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text())


def test_parse_actuals_fixture():
    rows = parse_actuals(load("fuelhh.json"))
    assert len(rows) == 4
    first = rows[0]
    assert first.start_time.tzinfo == UTC
    assert first.settlement_date == date(2026, 1, 15)
    assert isinstance(first.generation, int)


def test_parse_actuals_skips_other_fuels_and_nulls():
    raw = load("fuelhh.json")[:1]
    raw += [dict(raw[0], fuelType="CCGT"), dict(raw[0], generation=None)]
    assert len(parse_actuals(raw)) == 1


def test_parse_forecasts_fixture():
    rows = parse_forecasts(load("windfor.json"))
    assert len(rows) == 4
    assert rows[0].publish_time == datetime(2026, 1, 15, 7, 30, tzinfo=UTC)


def test_forecast_chunks_are_deduplicated():
    row = load("windfor.json")[0]
    calls: list[httpx.QueryParams] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params)
        # Simulate the inclusive range: every chunk returns the same boundary row.
        return httpx.Response(200, json=[row])

    async def run():
        transport = httpx.MockTransport(handler)
        async with ElexonClient(
            "https://example.test", httpx.AsyncClient(transport=transport)
        ) as c:
            return await c.wind_forecasts(
                datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 20, tzinfo=UTC)
            )

    result = asyncio.run(run())
    assert len(calls) == 3  # 7 + 7 + 5 days
    assert len(result) == 1


def test_retries_transient_errors(monkeypatch):
    monkeypatch.setattr("app.elexon.asyncio.sleep", _no_sleep)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=load("fuelhh.json"))

    async def run():
        transport = httpx.MockTransport(handler)
        async with ElexonClient(
            "https://example.test", httpx.AsyncClient(transport=transport)
        ) as c:
            return await c.wind_actuals(date(2026, 1, 15), date(2026, 1, 15))

    assert len(asyncio.run(run())) == 4
    assert attempts == 3


async def _no_sleep(_: float) -> None:
    return None
