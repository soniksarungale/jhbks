#!/usr/bin/env bash
# Build and (re)start WindSight on this server. Run from the repo root.
set -euo pipefail

cd "$(dirname "$0")/.."
WEB_ROOT=${WEB_ROOT:-/var/www/windsight}

echo "--> backend"
(cd backend && uv sync --locked --no-dev)

echo "--> frontend"
(cd frontend && npm ci --silent && npm run build)
sudo mkdir -p "$WEB_ROOT"
sudo rsync -a --delete frontend/dist/ "$WEB_ROOT/"

echo "--> api"
mkdir -p logs
if pm2 describe windsight >/dev/null 2>&1; then
  pm2 reload windsight --update-env
else
  pm2 start deploy/ecosystem.config.cjs
fi
pm2 save >/dev/null

for _ in $(seq 60); do
  curl -sf http://127.0.0.1:4600/api/health >/dev/null && { echo "up"; exit 0; }
  sleep 1
done
echo "api did not become healthy, see logs/error.log" >&2
exit 1
