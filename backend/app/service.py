"""Turns analysis results into API models. Holds the loaded dataset."""

import io
from datetime import date, time, timedelta
from functools import lru_cache
from typing import Any, cast

import numpy as np
import pandas as pd

from app import analysis as an
from app import schemas as s
from app.config import UK_TZ, Settings


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Rows as plain dicts with NaN/NaT replaced by None."""
    rows = cast(list[dict[str, Any]], df.to_dict("records"))
    return [{k: (None if pd.isna(v) else v) for k, v in r.items()} for r in rows]


def _int(v: Any) -> int | None:
    return None if v is None else int(v)


class WindService:
    def __init__(self, ds: an.Dataset, settings: Settings, fetched_at: str | None) -> None:
        self.ds = ds
        self.settings = settings
        self.fetched_at = fetched_at
        # Analysis results only depend on the inputs, and the dataset never
        # changes while the process is up, so memoise per instance.
        self._accuracy = lru_cache(maxsize=64)(self._compute_accuracy)
        self._table = lru_cache(maxsize=64)(self._compute_table)

    @property
    def days(self) -> list[date]:
        return an.decision_days(self.settings.decision_start, self.settings.decision_end)

    def evaluation_window(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        start, _ = an.delivery_window(self.settings.decision_start)
        _, end = an.delivery_window(self.settings.decision_end)
        return start, end

    def meta(self) -> s.Meta:
        return s.Meta(
            decision_start=self.settings.decision_start,
            decision_end=self.settings.decision_end,
            history_start=self.settings.history_start,
            default_cutoff=self.settings.default_cutoff.strftime("%H:%M"),
            timezone=str(UK_TZ),
            fetched_at=self.fetched_at,
        )

    def decision(self, day: date, cutoff: time) -> s.Decision:
        d = an.decision(self.ds, day, cutoff, self.settings.history_start)
        points = [
            s.ForecastPoint(
                time=r["start_time"],
                forecast=int(r["generation"]),
                lead_h=float(r["lead_h"]),
                p10=r["p10"],
                p90=r["p90"],
                band_n=int(r["band_n"]),
                actual=_int(r["actual"]),
                error=_int(r["error"]),
            )
            for r in _records(d.points)
        ]
        vintages = [s.Vintage(publish_time=p, points=_series(v)) for p, v in d.vintages.items()]
        return s.Decision(
            decision_day=day,
            delivery_day=day + timedelta(days=1),
            cutoff=d.cutoff,
            publish_time=d.publish_time,
            points=points,
            vintages=vintages,
            actuals=_series(d.actuals),
            kpis=_kpis(d.points),
            hindsight=s.Summary(**an.summary(d.points)),
        )

    def _compute_table(self, cutoff: time) -> pd.DataFrame:
        return an.decision_table(self.ds, self.days, cutoff, self.settings.history_start)

    def _compute_accuracy(self, cutoff: time) -> s.Accuracy:
        tbl = self._table(cutoff)
        label = cutoff.strftime("%H:%M")
        if tbl.empty:
            return s.Accuracy(
                cutoff=label, summary=s.Summary(n=0), by_hour=[], histogram=[], scatter=[], daily=[]
            )
        matched = tbl.dropna(subset=["actual"])
        return s.Accuracy(
            cutoff=label,
            summary=s.Summary(**an.summary(tbl)),
            by_hour=[s.HourStat(**r) for r in _records(an.by_local_hour(tbl))],
            histogram=[s.Bin(**b) for b in an.histogram(tbl["error"])],
            scatter=[
                s.ScatterPoint(
                    time=r["start_time"], forecast=int(r["generation"]), actual=int(r["actual"])
                )
                for r in _records(matched)
            ],
            daily=[s.DayRow(**r) for r in _records(an.daily(tbl, self.ds))],
        )

    def accuracy(self, cutoff: time) -> s.Accuracy:
        result: s.Accuracy = self._accuracy(cutoff)
        return result

    def lead_time(self) -> s.LeadTime:
        start, end = self.evaluation_window()
        curve = an.lead_curve(self.ds, start, end)
        return s.LeadTime(curve=[s.LeadStat(**r) for r in _records(curve)])

    def horizon(self, hours: float) -> s.Horizon:
        start, end = self.evaluation_window()
        h = an.at_horizon(self.ds, hours, start, end)
        return s.Horizon(
            hours=hours,
            summary=s.Summary(**an.summary(h)),
            points=[
                s.HorizonPoint(
                    time=r["start_time"],
                    publish_time=r["publish_time"],
                    forecast=int(r["generation"]),
                    actual=_int(r["actual"]),
                )
                for r in _records(h)
            ],
        )

    def export_csv(self, cutoff: time) -> str:
        tbl = self._table(cutoff)
        if tbl.empty:
            return ""
        out = pd.DataFrame(
            {
                "decision_day": tbl["decision_day"],
                "publish_time_utc": tbl["publish_time"].dt.strftime("%Y-%m-%dT%H:%MZ"),
                "target_time_utc": tbl["start_time"].dt.strftime("%Y-%m-%dT%H:%MZ"),
                "target_time_uk": tbl["start_time"]
                .dt.tz_convert(UK_TZ)
                .dt.strftime("%Y-%m-%d %H:%M"),
                "lead_h": tbl["lead_h"].round(2),
                "forecast_mw": tbl["generation"],
                "p10_mw": tbl["p10"].round(0),
                "p90_mw": tbl["p90"].round(0),
                "actual_mw": tbl["actual"],
                "error_mw": tbl["error"],
            }
        )
        buf = io.StringIO()
        out.to_csv(buf, index=False)
        return buf.getvalue()


def _series(df: pd.DataFrame) -> list[s.SeriesPoint]:
    return [s.SeriesPoint(time=r["start_time"], value=int(r["generation"])) for r in _records(df)]


def _kpis(pts: pd.DataFrame) -> s.DecisionKpis | None:
    if pts.empty:
        return None
    gen = pts["generation"].to_numpy(dtype=float)
    times: list[pd.Timestamp] = pts["start_time"].tolist()
    peak, low = int(gen.argmax()), int(gen.argmin())
    ramps = np.abs(np.diff(gen))
    ramp = int(ramps.argmax()) + 1 if ramps.size else None
    return s.DecisionKpis(
        forecast_mwh=float(gen.sum()),  # hourly MW points, 1 h each
        peak_mw=int(gen[peak]),
        peak_time=times[peak],
        min_mw=int(gen[low]),
        min_time=times[low],
        max_ramp_mw=int(ramps[ramp - 1]) if ramp is not None else 0,
        max_ramp_time=times[ramp] if ramp is not None else None,
    )
