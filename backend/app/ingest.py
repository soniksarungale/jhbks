"""Pull the data we need from Elexon into SQLite.

uv run python -m app.ingest
"""

import asyncio
import logging
from datetime import UTC, datetime, time, timedelta

from app import store
from app.config import UK_TZ, Settings, get_settings
from app.elexon import ElexonClient

log = logging.getLogger(__name__)


def data_window(settings: Settings) -> tuple[datetime, datetime]:
    """Earliest target time and latest delivery end we need data for (UTC)."""
    first = datetime.combine(settings.history_start, time(0), UK_TZ)
    last_delivery = settings.decision_end + timedelta(days=1)
    end = datetime.combine(last_delivery + timedelta(days=1), time(0), UK_TZ)
    return first.astimezone(UTC), end.astimezone(UTC)


async def ingest(settings: Settings) -> tuple[int, int]:
    first_target, delivery_end = data_window(settings)

    # Forecasts are published up to ~3 days ahead of the target, so start a few
    # days early to have every lead time for the first targets. Nothing
    # published after the last delivery day ends can inform a decision.
    published_from = first_target - timedelta(days=3)
    published_to = delivery_end

    async with ElexonClient(settings.elexon_base_url) as client:
        actuals, forecasts = await asyncio.gather(
            client.wind_actuals(
                (first_target - timedelta(days=1)).date(),
                (delivery_end + timedelta(days=1)).date(),
            ),
            client.wind_forecasts(published_from, published_to),
        )

    with store.connect(settings.db_path) as conn:
        n_actuals = store.save_actuals(conn, actuals)
        n_forecasts = store.save_forecasts(conn, forecasts)
        store.set_meta(conn, "fetched_at", datetime.now(UTC).isoformat(timespec="seconds"))
    log.info("stored %d actuals and %d forecast rows", n_actuals, n_forecasts)
    return n_actuals, n_forecasts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(ingest(get_settings()))


if __name__ == "__main__":
    main()
