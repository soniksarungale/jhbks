from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(settings: Settings, populated_db: Path) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_meta(client):
    body = client.get("/api/meta").json()
    assert body["default_cutoff"] == "09:20"
    assert body["decision_start"] == "2026-01-01"


def test_decision(client):
    r = client.get("/api/decision", params={"day": "2026-01-01"})
    assert r.status_code == 200
    body = r.json()
    assert body["delivery_day"] == "2026-01-02"
    assert body["publish_time"] == "2026-01-01T07:30:00Z"
    assert len(body["points"]) == 24
    assert len(body["actuals"]) == 48
    assert body["kpis"]["forecast_mwh"] > 0
    assert body["hindsight"]["n"] == 24


def test_decision_custom_cutoff_uses_later_publish(client):
    body = client.get("/api/decision", params={"day": "2026-01-01", "cutoff": "12:00"}).json()
    assert body["publish_time"] == "2026-01-01T11:30:00Z"


@pytest.mark.parametrize(
    "params",
    [
        {"day": "2025-12-31"},
        {"day": "2026-02-01"},
        {"day": "not-a-date"},
        {"day": "2026-01-01", "cutoff": "25:00"},
    ],
)
def test_decision_rejects_bad_input(client, params):
    assert client.get("/api/decision", params=params).status_code == 422


def test_accuracy(client):
    body = client.get("/api/accuracy").json()
    assert body["cutoff"] == "09:20"
    assert body["summary"]["n"] == 48
    assert body["summary"]["bias"] > 0
    assert len(body["daily"]) == 2
    assert len(body["by_hour"]) == 24
    assert sum(b["count"] for b in body["histogram"]) == 48


def test_lead_time(client):
    curve = client.get("/api/lead-time").json()["curve"]
    assert curve[0]["lead_h"] == 0
    assert all(p["n"] > 0 for p in curve)


def test_horizon(client):
    body = client.get("/api/horizon", params={"hours": 24}).json()
    assert body["summary"]["n"] == 48
    assert client.get("/api/horizon", params={"hours": 49}).status_code == 422


def test_export_csv(client):
    r = client.get("/api/export/decisions.csv", params={"cutoff": "09:20"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "windsight-decisions-0920.csv" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("decision_day,publish_time_utc,target_time_utc")
    assert len(lines) == 49


def test_serves_frontend_with_spa_fallback(settings, populated_db, tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>app</html>")
    (static / "favicon.svg").write_text("<svg/>")
    settings.static_dir = static

    with TestClient(create_app(settings)) as c:
        assert c.get("/").text == "<html>app</html>"
        assert c.get("/favicon.svg").text == "<svg/>"
        assert c.get("/some/deep/link").text == "<html>app</html>"
        assert c.get("/..%2f..%2fetc/passwd").text == "<html>app</html>"
        assert c.get("/api/nope").status_code == 404
