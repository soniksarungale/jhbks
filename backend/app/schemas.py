from datetime import date, datetime

from pydantic import BaseModel


class Health(BaseModel):
    status: str
    fetched_at: str | None


class Meta(BaseModel):
    decision_start: date
    decision_end: date
    history_start: date
    default_cutoff: str
    timezone: str
    fetched_at: str | None


class Summary(BaseModel):
    n: int
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None
    p50_abs: float | None = None
    p90_abs: float | None = None
    max_abs: float | None = None
    mean_actual: float | None = None
    nmae: float | None = None
    band_coverage: float | None = None


class ForecastPoint(BaseModel):
    time: datetime
    forecast: int
    lead_h: float
    p10: float | None
    p90: float | None
    band_n: int
    actual: int | None
    error: int | None


class SeriesPoint(BaseModel):
    time: datetime
    value: int


class Vintage(BaseModel):
    publish_time: datetime
    points: list[SeriesPoint]


class DecisionKpis(BaseModel):
    forecast_mwh: float
    peak_mw: int
    peak_time: datetime
    min_mw: int
    min_time: datetime
    max_ramp_mw: int
    max_ramp_time: datetime | None


class Decision(BaseModel):
    decision_day: date
    delivery_day: date
    cutoff: datetime
    publish_time: datetime | None
    points: list[ForecastPoint]
    vintages: list[Vintage]
    actuals: list[SeriesPoint]
    kpis: DecisionKpis | None
    hindsight: Summary


class HourStat(BaseModel):
    hour: int
    mae: float
    bias: float
    p10: float
    p90: float
    n: int


class Bin(BaseModel):
    lo: float
    hi: float
    count: int


class ScatterPoint(BaseModel):
    time: datetime
    forecast: int
    actual: int


class DayRow(BaseModel):
    decision_day: date
    delivery_day: date
    publish_time: datetime
    forecast_mwh: float
    actual_mwh: float | None
    mae: float | None
    bias: float | None
    max_abs: float | None
    complete: bool


class Accuracy(BaseModel):
    cutoff: str
    summary: Summary
    by_hour: list[HourStat]
    histogram: list[Bin]
    scatter: list[ScatterPoint]
    daily: list[DayRow]


class LeadStat(BaseModel):
    lead_h: int
    mae: float
    rmse: float
    bias: float
    p10: float
    p90: float
    n: int


class LeadTime(BaseModel):
    curve: list[LeadStat]


class HorizonPoint(BaseModel):
    time: datetime
    publish_time: datetime
    forecast: int
    actual: int | None


class Horizon(BaseModel):
    hours: float
    summary: Summary
    points: list[HorizonPoint]
