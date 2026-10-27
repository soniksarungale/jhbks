from datetime import date, time
from pathlib import Path

import pandas as pd
import pytest

from app import analysis as an
from app import store
from app.config import Settings
from app.elexon import Actual, Forecast


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def make_dataset(
    actuals: list[tuple[str, int]], forecasts: list[tuple[str, str, int]]
) -> an.Dataset:
    act = pd.DataFrame(
        {"start_time": [ts(t) for t, _ in actuals], "generation": [g for _, g in actuals]}
    )
    fc = pd.DataFrame(
        {
            "publish_time": [ts(p) for p, _, _ in forecasts],
            "start_time": [ts(t) for _, t, _ in forecasts],
            "generation": [g for _, _, g in forecasts],
        }
    )
    return an.prepare(act, fc)


def synthetic_frames(
    start: str = "2025-12-28", end: str = "2026-01-04", actual_mw: int = 10_000, bias: int = 500
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Flat actuals; 8 publishes a day that over-forecast by `bias` plus 10 MW per lead hour."""
    halfhours = pd.date_range(start, end, freq="30min", tz="UTC", inclusive="left")
    act = pd.DataFrame({"start_time": halfhours, "generation": actual_mw})

    rows = []
    for day in pd.date_range(start, end, freq="D", tz="UTC", inclusive="left"):
        for hhmm in ("02:30", "04:30", "07:30", "09:30", "11:30", "15:30", "18:30", "22:30"):
            pub = day + pd.Timedelta(hhmm + ":00")
            for h in range(-2, 48):
                target = pub.floor("h") + pd.Timedelta(hours=h + 1)
                lead = (target - pub) / pd.Timedelta(hours=1)
                rows.append((pub, target, actual_mw + bias + int(lead * 10)))
    fc = pd.DataFrame(rows, columns=["publish_time", "start_time", "generation"])
    return act, fc


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "test.db",
        decision_start=date(2026, 1, 1),
        decision_end=date(2026, 1, 2),
        history_start=date(2025, 12, 28),
        default_cutoff=time(9, 20),
    )


@pytest.fixture
def populated_db(settings: Settings) -> Path:
    act, fc = synthetic_frames()
    with store.connect(settings.db_path) as conn:
        store.save_actuals(
            conn,
            (
                Actual(r.start_time.to_pydatetime(), r.start_time.date(), 1, int(r.generation))
                for r in act.itertuples()
            ),
        )
        store.save_forecasts(
            conn,
            (
                Forecast(
                    r.publish_time.to_pydatetime(), r.start_time.to_pydatetime(), int(r.generation)
                )
                for r in fc.itertuples()
            ),
        )
        store.set_meta(conn, "fetched_at", "2026-02-02T00:00:00+00:00")
    return settings.db_path
