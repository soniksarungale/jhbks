from datetime import date, time

import numpy as np
import pandas as pd
import pytest

from app import analysis as an
from tests.conftest import make_dataset, synthetic_frames, ts


def test_prepare_drops_hours_before_publish_and_signs_error():
    ds = make_dataset(
        actuals=[("2026-01-01T10:00Z", 1000), ("2026-01-01T12:00Z", 2000)],
        forecasts=[
            ("2026-01-01T11:30Z", "2026-01-01T10:00Z", 999),  # restated past hour
            ("2026-01-01T11:30Z", "2026-01-01T12:00Z", 2300),
        ],
    )
    assert len(ds.forecasts) == 1
    row = ds.matched.iloc[0]
    assert row["lead_h"] == 0.5
    assert row["error"] == 300  # forecast above actual -> positive
    assert row["known_at"] == ts("2026-01-01T12:30Z")


def test_matches_on_the_hour_only():
    ds = make_dataset(
        actuals=[("2026-01-01T12:00Z", 2000), ("2026-01-01T12:30Z", 9999)],
        forecasts=[("2026-01-01T07:30Z", "2026-01-01T12:00Z", 2100)],
    )
    assert ds.matched["actual"].tolist() == [2000]


def test_delivery_window_gmt():
    start, end = an.delivery_window(date(2026, 1, 15))
    assert (start, end) == (ts("2026-01-16T00:00Z"), ts("2026-01-17T00:00Z"))


def test_delivery_window_handles_clock_change():
    # Clocks go forward on 29 March 2026: a 23 hour UK day.
    start, end = an.delivery_window(date(2026, 3, 28))
    assert start == ts("2026-03-29T00:00Z")
    assert end == ts("2026-03-29T23:00Z")


def test_cutoff_is_uk_local_time():
    assert an.to_utc(date(2026, 1, 15), time(9, 20)) == ts("2026-01-15T09:20Z")
    assert an.to_utc(date(2026, 7, 15), time(9, 20)) == ts("2026-07-15T08:20Z")


def test_latest_publish_respects_cutoff():
    ds = make_dataset(
        actuals=[],
        forecasts=[
            ("2026-01-15T04:30Z", "2026-01-16T00:00Z", 1),
            ("2026-01-15T07:30Z", "2026-01-16T00:00Z", 2),
            ("2026-01-15T09:30Z", "2026-01-16T00:00Z", 3),
        ],
    )
    start = ts("2026-01-16T00:00Z")
    assert an.latest_publish(ds, ts("2026-01-15T09:20Z"), start) == ts("2026-01-15T07:30Z")
    # Published exactly at the cutoff counts as available.
    assert an.latest_publish(ds, ts("2026-01-15T09:30Z"), start) == ts("2026-01-15T09:30Z")
    assert an.latest_publish(ds, ts("2026-01-15T00:00Z"), start) is None


def test_error_quantiles_ignore_errors_not_yet_known():
    act, fc = synthetic_frames()
    ds = an.prepare(act, fc)
    known_by = ts("2026-01-02T09:20Z")
    since = ts("2025-12-28T00:00Z")
    leads = np.array([20.0])
    before = an.error_quantiles(ds, leads, known_by, since)

    # A huge error on a target whose actual only arrives later must not change the band.
    poisoned = ds.matched.copy()
    late = poisoned["known_at"] > known_by
    poisoned.loc[late, "error"] = 1_000_000
    ds2 = an.Dataset(ds.actuals, ds.forecasts, poisoned)
    after = an.error_quantiles(ds2, leads, known_by, since)

    np.testing.assert_array_equal(before.q90, after.q90)
    assert before.n[0] == after.n[0] > 0


def test_band_brackets_forecast_with_constant_bias():
    act, fc = synthetic_frames(bias=500)
    ds = an.prepare(act, fc)
    d = an.decision(ds, date(2026, 1, 2), time(9, 20), date(2025, 12, 28))
    pts = d.points
    assert len(pts) == 24
    assert d.publish_time == ts("2026-01-02T07:30Z")
    # Errors are deterministic (bias + 10 MW per lead hour), so the band sits
    # around the true value and lower bound never exceeds upper bound.
    assert (pts["p10"] <= pts["p90"]).all()
    assert ((pts["p10"] <= pts["actual"]) & (pts["actual"] <= pts["p90"])).mean() > 0.5


def test_band_is_clipped_at_zero():
    act, fc = synthetic_frames(actual_mw=100, bias=5_000)
    ds = an.prepare(act, fc)
    d = an.decision(ds, date(2026, 1, 2), time(9, 20), date(2025, 12, 28))
    assert (d.points["p10"] >= 0).all()


def test_band_missing_when_history_too_thin():
    act, fc = synthetic_frames()
    ds = an.prepare(act, fc)
    # History starts after the decision, so there is nothing to learn from.
    d = an.decision(ds, date(2026, 1, 2), time(9, 20), date(2026, 1, 3))
    assert d.points["p10"].isna().all()
    assert (d.points["band_n"] == 0).all()


def test_decision_vintages_are_earlier_publishes():
    act, fc = synthetic_frames()
    ds = an.prepare(act, fc)
    d = an.decision(ds, date(2026, 1, 2), time(9, 20), date(2025, 12, 28), n_vintages=3)
    assert list(d.vintages) == [
        ts("2026-01-01T22:30Z"),
        ts("2026-01-02T02:30Z"),
        ts("2026-01-02T04:30Z"),
    ]
    assert all(p < d.publish_time for p in d.vintages)


def test_summary_hand_example():
    df = pd.DataFrame(
        {
            "generation": [110, 90, 100, 120],
            "actual": [100, 100, 100, 100],
            "error": [10, -10, 0, 20],
            "p10": [95, 95, 95, 105],
            "p90": [105, 105, 105, 130],
        }
    )
    s = an.summary(df)
    assert s["n"] == 4
    assert s["mae"] == 10
    assert s["bias"] == 5
    assert s["rmse"] == pytest.approx(np.sqrt((100 + 100 + 0 + 400) / 4))
    assert s["nmae"] == pytest.approx(0.1)
    assert s["band_coverage"] == 0.75


def test_summary_empty():
    df = pd.DataFrame({"generation": [1], "actual": [np.nan], "error": [np.nan]})
    assert an.summary(df) == {"n": 0}


def test_at_horizon_picks_latest_publish_old_enough():
    ds = make_dataset(
        actuals=[("2026-01-02T12:00Z", 1000)],
        forecasts=[
            ("2026-01-01T07:30Z", "2026-01-02T12:00Z", 1),  # 28.5 h ahead
            ("2026-01-01T11:30Z", "2026-01-02T12:00Z", 2),  # 24.5 h ahead
            ("2026-01-01T15:30Z", "2026-01-02T12:00Z", 3),  # 20.5 h ahead
        ],
    )
    out = an.at_horizon(ds, 24, ts("2026-01-02T00:00Z"), ts("2026-01-03T00:00Z"))
    assert out["generation"].tolist() == [2]
    assert out["publish_time"].tolist() == [ts("2026-01-01T11:30Z")]


def test_lead_curve_buckets_by_whole_hour():
    ds = make_dataset(
        actuals=[("2026-01-02T00:00Z", 100), ("2026-01-02T01:00Z", 100)],
        forecasts=[
            ("2026-01-01T22:30Z", "2026-01-02T00:00Z", 110),  # 1.5 h
            ("2026-01-01T23:25Z", "2026-01-02T01:00Z", 130),  # 1.58 h, late publish
        ],
    )
    curve = an.lead_curve(ds, ts("2026-01-02T00:00Z"), ts("2026-01-03T00:00Z"))
    assert curve["lead_h"].tolist() == [1]
    assert curve["n"].tolist() == [2]
    assert curve["bias"].tolist() == [20]


def test_histogram_counts_everything():
    errors = pd.Series([-600, -10, 0, 499, 500, 2000, np.nan])
    bins = an.histogram(errors, bin_mw=500)
    assert sum(b["count"] for b in bins) == 6
    assert bins[0]["lo"] == -1000
    assert all(b["hi"] - b["lo"] == 500 for b in bins)


def test_daily_energy():
    act, fc = synthetic_frames(actual_mw=1000, bias=0)
    ds = an.prepare(act, fc)
    tbl = an.decision_table(ds, [date(2026, 1, 1)], time(9, 20), date(2025, 12, 28))
    day = an.daily(tbl, ds).iloc[0]
    assert day["actual_mwh"] == 24_000
    assert day["complete"]
