import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import analysis, store
from app.api import router
from app.config import Settings, get_settings
from app.ingest import ingest
from app.service import WindService

log = logging.getLogger("windsight")


def load_service(settings: Settings) -> WindService:
    with store.connect(settings.db_path) as conn:
        ds = analysis.prepare(store.load_actuals(conn), store.load_forecasts(conn))
        fetched_at = store.get_meta(conn, "fetched_at")
    log.info("loaded %d forecast rows, %d actuals", len(ds.forecasts), len(ds.actuals))
    return WindService(ds, settings, fetched_at)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with store.connect(settings.db_path) as conn:
            populated = store.is_populated(conn)
        if not populated:
            log.info("no data in %s, fetching from Elexon", settings.db_path)
            await ingest(settings)
        service = load_service(settings)
        service.accuracy(settings.default_cutoff)  # warm the default view
        app.state.service = service
        yield

    app = FastAPI(title="WindSight API", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def access_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - started) * 1000
        if request.url.path.startswith("/api"):
            log.info("%s %s %d %.1fms", request.method, request.url.path, response.status_code, ms)
        response.headers["Server-Timing"] = f"app;dur={ms:.1f}"
        return response

    app.include_router(router)

    if settings.static_dir:
        mount_frontend(app, settings.static_dir)
    return app


def mount_frontend(app: FastAPI, static_dir: Path) -> None:
    """Serve the built SPA (used in the Docker image; nginx does this in prod)."""
    index = static_dir / "index.html"
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404)
        candidate = (static_dir / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(static_dir.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

app = create_app()
