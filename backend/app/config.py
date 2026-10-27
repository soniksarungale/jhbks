from datetime import date, time
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

UK_TZ = ZoneInfo("Europe/London")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WINDSIGHT_", env_file=".env")

    elexon_base_url: str = "https://data.elexon.co.uk/bmrs/api/v1"
    db_path: Path = Path("data/windsight.db")
    static_dir: Path | None = None

    # Purchase decisions in scope. Delivery is always the following day.
    decision_start: date = date(2026, 1, 1)
    decision_end: date = date(2026, 1, 31)

    # Forecast errors from this date onward feed the uncertainty band, so the
    # first decision days already have a month of history behind them.
    history_start: date = date(2025, 12, 1)

    # EPEX GB day-ahead auction gate closure, UK local time.
    default_cutoff: time = time(9, 20)


@lru_cache
def get_settings() -> Settings:
    return Settings()
