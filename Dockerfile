# Build the frontend, then serve it and the API from one Python image.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/app ./app
COPY --from=web /web/dist ./static

# Data is fetched from Elexon on first start and kept in /data.
ENV WINDSIGHT_STATIC_DIR=/app/static \
    WINDSIGHT_DB_PATH=/data/windsight.db
RUN useradd --system --uid 10001 app && mkdir /data && chown app /data
USER app
VOLUME /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
