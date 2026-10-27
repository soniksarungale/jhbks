"""Forecast selection and error analysis.

Conventions used throughout:
- All timestamps are tz-aware UTC; days and clock times from users are UK local.
- A forecast for hour HH:00 is compared with the actual for the settlement
  period that starts at HH:00.
- error = forecast - actual. Positive means wind came in below forecast, i.e.
  the desk would have under-bought.
- An actual becomes known when its half-hour ends (start + 30 min).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from app.config import UK_TZ

ACTUAL_DELAY = pd.Timedelta(minutes=30)
BAND_QUANTILES = (0.1, 0.5, 0.9)
LEAD_WINDOW_H = 3.0
MIN_BAND_SAMPLES = 30


@dataclass(frozen=True)
class Dataset:
    actuals: pd.DataFrame  # start_time, generation
    forecasts: pd.DataFrame  # publish_time, start_time, generation, lead_h
    matched: pd.DataFrame  # forecasts with actual, error, known_at


def prepare(actuals: pd.DataFrame, forecasts: pd.DataFrame) -> Dataset:
    fc = forecasts.copy()
    fc["lead_h"] = (fc["start_time"] - fc["publish_time"]).dt.total_seconds() / 3600
    # Each publish also restates the hours before it; those aren't forecasts.
    fc = fc[fc["lead_h"] >= 0].reset_index(drop=True)

    act = actuals.rename(columns={"generation": "actual"})
    matched = fc.merge(act, on="start_time", how="inner")
    matched["error"] = matched["generation"] - matched["actual"]
    matched["known_at"] = matched["start_time"] + ACTUAL_DELAY
    return Dataset(actuals=actuals, forecasts=fc, matched=matched)


def to_utc(day: date, at: time) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(day, at, UK_TZ)).tz_convert("UTC")


def delivery_window(decision_day: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    """UK-local delivery day following the decision day, as [start, end) in UTC."""
    delivery = decision_day + timedelta(days=1)
    return to_utc(delivery, time(0)), to_utc(delivery + timedelta(days=1), time(0))


def latest_publish(ds: Dataset, as_of: pd.Timestamp, start: pd.Timestamp) -> pd.Timestamp | None:
    """Most recent publish at or before as_of that has any forecast at or after start."""
    fc = ds.forecasts
    candidates = fc.loc[(fc["publish_time"] <= as_of) & (fc["start_time"] >= start), "publish_time"]
    return None if candidates.empty else candidates.max()


def forecast_for(
    ds: Dataset, publish_time: pd.Timestamp, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    fc = ds.forecasts
    mask = (
        (fc["publish_time"] == publish_time)
        & (fc["start_time"] >= start)
        & (fc["start_time"] < end)
    )
    return fc.loc[mask, ["start_time", "generation", "lead_h"]].reset_index(drop=True)


@dataclass(frozen=True)
class ErrorQuantiles:
    q10: np.ndarray
    q50: np.ndarray
    q90: np.ndarray
    n: np.ndarray


def error_quantiles(
    ds: Dataset,
    leads: np.ndarray,
    known_by: pd.Timestamp,
    since: pd.Timestamp,
    window_h: float = LEAD_WINDOW_H,
) -> ErrorQuantiles:
    """Empirical error quantiles at each lead time, using only verified errors.

    Pools errors whose lead is within +/- window_h of the requested lead, from
    targets at or after `since` whose actual was known by `known_by`.
    """
    m = ds.matched
    hist = m[(m["known_at"] <= known_by) & (m["start_time"] >= since)]
    h_leads = hist["lead_h"].to_numpy()
    h_err = hist["error"].to_numpy(dtype=float)

    out = np.full((3, len(leads)), np.nan)
    n = np.zeros(len(leads), dtype=int)
    for i, lead in enumerate(leads):
        sample = h_err[np.abs(h_leads - lead) <= window_h]
        n[i] = sample.size
        if sample.size >= MIN_BAND_SAMPLES:
            out[:, i] = np.quantile(sample, BAND_QUANTILES)
    return ErrorQuantiles(q10=out[0], q50=out[1], q90=out[2], n=n)


def with_band(
    ds: Dataset, fc: pd.DataFrame, known_by: pd.Timestamp, since: pd.Timestamp
) -> pd.DataFrame:
    """Add P10/P90 generation bounds implied by historical errors at each lead."""
    q = error_quantiles(ds, fc["lead_h"].to_numpy(), known_by, since)
    out = fc.copy()
    # actual = forecast - error, so the low generation bound uses the high error quantile
    out["p10"] = np.clip(out["generation"] - q.q90, 0, None)
    out["p90"] = np.clip(out["generation"] - q.q10, 0, None)
    out["band_n"] = q.n
    return out


def attach_actuals(ds: Dataset, df: pd.DataFrame) -> pd.DataFrame:
    act = ds.actuals.rename(columns={"generation": "actual"})
    out = df.merge(act, on="start_time", how="left")
    out["error"] = out["generation"] - out["actual"]
    return out


@dataclass(frozen=True)
class Decision:
    decision_day: date
    cutoff: pd.Timestamp
    delivery_start: pd.Timestamp
    delivery_end: pd.Timestamp
    publish_time: pd.Timestamp | None
    points: pd.DataFrame  # start_time, generation, lead_h, p10, p90, band_n, actual, error
    vintages: dict[pd.Timestamp, pd.DataFrame]
    actuals: pd.DataFrame  # half-hourly start_time, generation


def decision(
    ds: Dataset,
    decision_day: date,
    cutoff: time,
    history_start: date,
    n_vintages: int = 4,
) -> Decision:
    cutoff_ts = to_utc(decision_day, cutoff)
    start, end = delivery_window(decision_day)
    since = to_utc(history_start, time(0))

    publish = latest_publish(ds, cutoff_ts, start)
    if publish is None:
        points = pd.DataFrame(
            columns=[
                "start_time",
                "generation",
                "lead_h",
                "p10",
                "p90",
                "band_n",
                "actual",
                "error",
            ]
        )
    else:
        points = attach_actuals(
            ds, with_band(ds, forecast_for(ds, publish, start, end), cutoff_ts, since)
        )

    fc = ds.forecasts
    earlier = (
        fc.loc[
            (fc["publish_time"] < (publish if publish is not None else cutoff_ts))
            & (fc["start_time"] >= start)
            & (fc["start_time"] < end),
            "publish_time",
        ]
        .drop_duplicates()
        .sort_values()
        .tail(n_vintages)
    )
    vintages = {p: forecast_for(ds, p, start, end) for p in earlier}

    act = ds.actuals
    half_hourly = act[(act["start_time"] >= start) & (act["start_time"] < end)].reset_index(
        drop=True
    )

    return Decision(
        decision_day=decision_day,
        cutoff=cutoff_ts,
        delivery_start=start,
        delivery_end=end,
        publish_time=publish,
        points=points,
        vintages=vintages,
        actuals=half_hourly,
    )


def decision_days(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def decision_table(
    ds: Dataset, days: list[date], cutoff: time, history_start: date
) -> pd.DataFrame:
    """Every decision-time forecast in the period, matched to actuals, with bands."""
    frames = []
    for day in days:
        d = decision(ds, day, cutoff, history_start, n_vintages=0)
        if d.points.empty:
            continue
        pts = d.points.copy()
        pts["decision_day"] = day
        pts["publish_time"] = d.publish_time
        frames.append(pts)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def summary(df: pd.DataFrame) -> dict[str, float | int | None]:
    """Headline metrics for a frame with generation, actual, error (and optionally p10/p90)."""
    m = df.dropna(subset=["actual", "error"])
    if m.empty:
        return {"n": 0}
    err = m["error"].to_numpy(dtype=float)
    abs_err = np.abs(err)
    mean_actual = float(m["actual"].mean())
    out: dict[str, float | int | None] = {
        "n": int(err.size),
        "mae": float(abs_err.mean()),
        "rmse": float(np.sqrt((err**2).mean())),
        "bias": float(err.mean()),
        "p50_abs": float(np.quantile(abs_err, 0.5)),
        "p90_abs": float(np.quantile(abs_err, 0.9)),
        "max_abs": float(abs_err.max()),
        "mean_actual": mean_actual,
        "nmae": float(abs_err.mean() / mean_actual) if mean_actual else None,
    }
    if {"p10", "p90"} <= set(m.columns):
        banded = m.dropna(subset=["p10", "p90"])
        inside = (banded["actual"] >= banded["p10"]) & (banded["actual"] <= banded["p90"])
        out["band_coverage"] = float(inside.mean()) if len(banded) else None
    return out


def by_local_hour(df: pd.DataFrame) -> pd.DataFrame:
    m = df.dropna(subset=["error"]).copy()
    m["hour"] = m["start_time"].dt.tz_convert(UK_TZ).dt.hour
    g = m.groupby("hour")["error"]
    out = pd.DataFrame(
        {
            "mae": g.apply(lambda s: s.abs().mean()),
            "bias": g.mean(),
            "p10": g.quantile(0.1),
            "p90": g.quantile(0.9),
            "n": g.size(),
        }
    )
    return out.reset_index()


def histogram(errors: pd.Series, bin_mw: int = 500) -> list[dict[str, float]]:
    e = errors.dropna().to_numpy(dtype=float)
    if e.size == 0:
        return []
    lo = np.floor(e.min() / bin_mw) * bin_mw
    hi = np.ceil(e.max() / bin_mw) * bin_mw + bin_mw
    counts, edges = np.histogram(e, bins=np.arange(lo, hi + 1, bin_mw))
    return [
        {"lo": float(a), "hi": float(b), "count": int(c)}
        for a, b, c in zip(edges[:-1], edges[1:], counts, strict=True)
    ]


def daily(df: pd.DataFrame, ds: Dataset) -> pd.DataFrame:
    """Per decision day stats. Forecast energy from hourly points; actual energy
    from the half-hourly outturn so it reflects what was actually generated."""
    rows = []
    days: list[date] = sorted(set(df["decision_day"]))
    for day in days:
        g = df[df["decision_day"] == day]
        start, end = delivery_window(day)
        act = ds.actuals[(ds.actuals["start_time"] >= start) & (ds.actuals["start_time"] < end)]
        m = g.dropna(subset=["error"])
        rows.append(
            {
                "decision_day": day,
                "delivery_day": day + timedelta(days=1),
                "publish_time": g["publish_time"].iloc[0],
                "forecast_mwh": float(g["generation"].sum()),
                "actual_mwh": float(act["generation"].sum() * 0.5) if len(act) else None,
                "mae": float(m["error"].abs().mean()) if len(m) else None,
                "bias": float(m["error"].mean()) if len(m) else None,
                "max_abs": float(m["error"].abs().max()) if len(m) else None,
                "complete": len(act) == round((end - start) / pd.Timedelta(minutes=30))
                and len(g) == round((end - start) / pd.Timedelta(hours=1)),
            }
        )
    return pd.DataFrame(rows)


def lead_curve(
    ds: Dataset, start: pd.Timestamp, end: pd.Timestamp, max_lead: float = 48
) -> pd.DataFrame:
    """Error statistics by whole-hour lead bucket for targets in [start, end).

    Bucket 0 holds leads in [0, 1), and so on. Publishes are normally at :30
    so most leads are x.5, but late publishes do happen.
    """
    m = ds.matched
    m = m[(m["start_time"] >= start) & (m["start_time"] < end) & (m["lead_h"] < max_lead)].copy()
    m["lead_bucket"] = np.floor(m["lead_h"]).astype(int)
    g = m.groupby("lead_bucket")["error"]
    out = pd.DataFrame(
        {
            "mae": g.apply(lambda s: s.abs().mean()),
            "rmse": g.apply(lambda s: float(np.sqrt((s**2).mean()))),
            "bias": g.mean(),
            "p10": g.quantile(0.1),
            "p90": g.quantile(0.9),
            "n": g.size(),
        }
    )
    return out.rename_axis("lead_h").reset_index()


def at_horizon(
    ds: Dataset, horizon_h: float, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    """For each target, the latest forecast published at least horizon_h before it."""
    fc = ds.forecasts
    fc = fc[(fc["start_time"] >= start) & (fc["start_time"] < end) & (fc["lead_h"] >= horizon_h)]
    if fc.empty:
        return pd.DataFrame(
            columns=["start_time", "publish_time", "generation", "lead_h", "actual", "error"]
        )
    idx = fc.groupby("start_time")["lead_h"].idxmin()
    picked = fc.loc[idx, ["start_time", "publish_time", "generation", "lead_h"]]
    return attach_actuals(ds, picked.sort_values("start_time").reset_index(drop=True))
