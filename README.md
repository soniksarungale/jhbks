# WindSight

A small web app for a UK utility's day-ahead trading desk. It answers two questions for every purchase decision in January 2026:

1. **What did the latest wind forecast say when we had to commit?** The newest national wind forecast published before the decision cutoff, for the next day, with a likely range around it.
2. **How far off are those forecasts?** Error statistics for exactly the forecasts the desk would have used, so the shortfall can be planned for rather than discovered.

**Live:** https://windsight.soniksarungale.com

Data comes only from Elexon BMRS: wind outturn ([FUELHH](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream), `fuelType=WIND`) and national wind forecasts ([WINDFOR](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)).

## What the analysis shows

Using the forecast available at the 09:20 gate closure (the 07:30 publish), across delivery days 2 Jan – 1 Feb:

| Metric | Value |
|---|---|
| Mean absolute error | 2.0 GW (18% of average wind output) |
| Bias (forecast − actual) | **+1.75 GW** – wind came in below forecast on 27 of 31 days |
| 1 hour in 10 misses by more than | 4.2 GW |
| Worst single hour | 6.9 GW |
| Actuals inside the P10–P90 range | 86% (target 80%) |

The bias is the main takeaway. It is already about 1.5 GW at under an hour of lead time, so it is not mainly forecast skill decaying with time. A likely cause is that FUELHH reports metered output after curtailment while the forecast is closer to available wind, but I haven't verified that against other data, since the brief limits us to these two datasets. Either way, a desk taking the forecast at face value would have been systematically short.

Error grows only gently with lead time: MAE goes from ~1.7 GW at 0 h to ~1.9 GW at 24 h and ~2.4 GW at 47 h.

## How it works

### Definitions

- **Decision day D** runs 1–31 Jan 2026. Delivery is the following UK day (D+1, 00:00–24:00 Europe/London), so delivery days are 2 Jan – 1 Feb.
- **Decision cutoff** defaults to 09:20 UK time, the EPEX GB day-ahead auction gate closure. It can be changed in the UI.
- **Forecast used** = the most recent WINDFOR publish at or before the cutoff. Each publish also restates the ~day before it, so rows with negative lead time are dropped.
- **Matching:** WINDFOR is hourly and FUELHH half-hourly. A forecast for HH:00 is compared with the actual for the settlement period starting at HH:00. The :30 actuals are still drawn on the chart.
- **Error** = forecast − actual. Positive means less wind than forecast, i.e. the desk under-bought.
- **Likely range (P10–P90)** for each hour: empirical 10th/90th percentiles of past errors at a similar lead time (±3 h), applied to the forecast and clipped at 0. Only errors whose actual was already published by the cutoff are used, so there is no look-ahead. History starts 1 Dec 2025 so the first January decisions already have a month of errors behind them.
- **Energy:** forecast energy sums the hourly points; actual energy sums half-hourly outturn × 0.5 h.

All of these live in `backend/app/analysis.py` and each has a test.

### Architecture

```
Elexon BMRS ──(once)──> ingest ──> SQLite ──> pandas (in memory) ──> FastAPI ──> React + ECharts
```

- **Backend:** FastAPI on Python 3.12, managed with uv. On first start it pulls Dec 2025 – Feb 2026 from Elexon (about 40k rows, ~5 s) into SQLite. It then loads everything into pandas once, because the dataset is small. Results are memoised per cutoff and the default view is warmed at startup.
- **Frontend:** React 19 + TypeScript (Vite), TanStack Query for fetching and caching, and ECharts (tree-shaken, canvas) for charts. View state (tab, day, cutoff, horizon) lives in the URL, so every view can be shared. Neighbouring days are prefetched.
- **Times:** stored and sent as UTC. The UI converts everything to UK local time regardless of the viewer's timezone, and charts are drawn on UK wall-clock time so ticks land on UK hours.

### API

| Endpoint | Returns |
|---|---|
| `GET /api/meta` | decision range, default cutoff, data fetch time |
| `GET /api/decision?day=2026-01-15&cutoff=09:20` | forecast used, P10–P90, earlier publishes, actuals, KPIs |
| `GET /api/accuracy?cutoff=09:20` | summary metrics, error by hour, histogram, scatter, daily table |
| `GET /api/lead-time` | error statistics by whole-hour lead time |
| `GET /api/horizon?hours=24` | latest forecast at least *h* hours before each target, with actuals |
| `GET /api/export/decisions.csv?cutoff=09:20` | every decision-time forecast hour with band, actual and error |
| `GET /api/health` | liveness |

Interactive docs are at `/docs` when running locally.

## Repository layout

```
backend/
  app/
    config.py       settings (env prefix WINDSIGHT_), date ranges, default cutoff
    elexon.py       async Elexon client: chunked requests, retries, parsing
    store.py        SQLite schema, save/load
    ingest.py       fetch from Elexon into SQLite (python -m app.ingest)
    analysis.py     forecast selection, error bands, metrics (pure functions)
    service.py      turns analysis results into API models, caching
    schemas.py      pydantic response models
    api.py          routes and input validation
    main.py         app factory, startup ingest, logging, static serving for Docker
  tests/            pytest: analysis, Elexon client, API (fixtures are trimmed real responses)
frontend/
  src/
    api.ts          typed API client (mirrors schemas.py)
    App.tsx         layout, tabs, URL state, cutoff control
    views/          DecisionView, AccuracyView, LeadTimeView
    components/     Chart (echarts wrapper), small UI pieces
    lib/            chart option builders, UK time and number formatting (+ tests)
deploy/
  ecosystem.config.cjs   pm2 process for the API
  nginx-windsight.conf   nginx site: static frontend + /api proxy
  deploy.sh              build and (re)start on the server
Dockerfile               multi-stage: build frontend, serve it and the API from one image
docker-compose.yml
.github/workflows/ci.yml lint, type check, tests, build, Docker image
.pre-commit-config.yaml  ruff, eslint, whitespace checks
```

## Running it

### Docker

```bash
docker compose up --build
# http://localhost:8000
```

The first start fetches data from Elexon into a named volume, so later starts are instant.

### Local development

Requires Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node 22.

```bash
# API on :4600
cd backend
uv sync
uv run python -m app.ingest          # optional; the API also fetches on first start
uv run uvicorn app.main:app --port 4600 --reload

# frontend on :5173, proxies /api to :4600
cd frontend
npm ci
npm run dev
```

### Checks

```bash
cd backend  && uv run ruff check . && uv run mypy app && uv run pytest
cd frontend && npm run lint && npm run typecheck && npm test
```

The same checks run in CI on every push, plus a Docker build. `pre-commit install` sets up the local hooks.

## Deployment

The live app runs on my own server rather than Vercel or Heroku: nginx serves the built frontend and proxies `/api` to the FastAPI process managed by pm2, with TLS from Let's Encrypt. `deploy/deploy.sh` rebuilds and restarts it. The Docker image is self-contained, so it can run on any container host as well.

## Limitations and next steps

- The P10–P90 range treats each hour independently. Summing hourly bounds would overstate the uncertainty of daily energy, so the UI doesn't show a daily range.
- Errors are pooled by lead time only. Conditioning on wind level (errors are smaller when output is low) or time of day would tighten the range.
- Given the persistent bias, an obvious next step is a bias-corrected forecast (forecast minus the trailing median error), evaluated on the same no-look-ahead basis.
- Only January 2026 is covered, as the brief asks. The date range is configuration, not code.

## Use of AI tools

I used Claude Code as a coding assistant during this project, for scaffolding, writing parts of the code and tests, and reviewing changes. I made the product and analysis decisions, including how decisions, cutoffs, matching and the no-look-ahead error band are defined, and I checked the results against the raw data.
