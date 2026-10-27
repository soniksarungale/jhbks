"""Thin client for the two Elexon BMRS datasets we use."""

import asyncio
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

log = logging.getLogger(__name__)

# WINDFOR returns 73 rows per publish and ~8 publishes a day; a week per
# request keeps responses around half a megabyte.
WINDFOR_CHUNK = timedelta(days=7)
FUELHH_CHUNK = timedelta(days=14)


@dataclass(frozen=True)
class Actual:
    start_time: datetime
    settlement_date: date
    settlement_period: int
    generation: int


@dataclass(frozen=True)
class Forecast:
    publish_time: datetime
    start_time: datetime
    generation: int


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def parse_actuals(rows: list[dict[str, Any]]) -> list[Actual]:
    return [
        Actual(
            start_time=parse_ts(r["startTime"]),
            settlement_date=date.fromisoformat(r["settlementDate"]),
            settlement_period=int(r["settlementPeriod"]),
            generation=int(r["generation"]),
        )
        for r in rows
        if r.get("fuelType") == "WIND" and r.get("generation") is not None
    ]


def parse_forecasts(rows: list[dict[str, Any]]) -> list[Forecast]:
    return [
        Forecast(
            publish_time=parse_ts(r["publishTime"]),
            start_time=parse_ts(r["startTime"]),
            generation=int(r["generation"]),
        )
        for r in rows
        if r.get("generation") is not None
    ]


def _date_chunks(start: date, end: date, step: timedelta) -> Iterator[tuple[date, date]]:
    cur = start
    while cur <= end:
        nxt = min(cur + step - timedelta(days=1), end)
        yield cur, nxt
        cur = nxt + timedelta(days=1)


def _time_chunks(
    start: datetime, end: datetime, step: timedelta
) -> Iterator[tuple[datetime, datetime]]:
    cur = start
    while cur < end:
        nxt = min(cur + step, end)
        yield cur, nxt
        cur = nxt


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ElexonClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=60)

    async def __aenter__(self) -> "ElexonClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any], retries: int = 3) -> list[Any]:
        url = f"{self._base}{path}"
        for attempt in range(1, retries + 1):
            try:
                resp = await self._client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                # Stream endpoints return a bare list; others wrap it in "data".
                return data if isinstance(data, list) else list(data.get("data", []))
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if attempt == retries:
                    raise
                log.warning("GET %s failed (%s), retry %d/%d", path, exc, attempt, retries)
                await asyncio.sleep(2**attempt)
        raise AssertionError("unreachable")

    async def wind_actuals(self, start: date, end: date) -> list[Actual]:
        """Half-hourly wind outturn for settlement dates start..end inclusive."""
        tasks = [
            self._get(
                "/datasets/FUELHH/stream",
                {
                    "settlementDateFrom": a.isoformat(),
                    "settlementDateTo": b.isoformat(),
                    "fuelType": "WIND",
                },
            )
            for a, b in _date_chunks(start, end, FUELHH_CHUNK)
        ]
        chunks = await asyncio.gather(*tasks)
        return [row for chunk in chunks for row in parse_actuals(chunk)]

    async def wind_forecasts(
        self, published_from: datetime, published_to: datetime
    ) -> list[Forecast]:
        """Every WINDFOR forecast published in [published_from, published_to)."""
        tasks = [
            self._get(
                "/datasets/WINDFOR/stream",
                {"publishDateTimeFrom": _iso(a), "publishDateTimeTo": _iso(b)},
            )
            for a, b in _time_chunks(published_from, published_to, WINDFOR_CHUNK)
        ]
        chunks = await asyncio.gather(*tasks)
        # Chunk boundaries are inclusive on both ends in the API, so dedupe.
        seen: dict[tuple[datetime, datetime], Forecast] = {}
        for chunk in chunks:
            for f in parse_forecasts(chunk):
                seen[(f.publish_time, f.start_time)] = f
        return list(seen.values())
