#!/usr/bin/env bash
# Production deploy: build -> migrate -> run the test suite -> go live. Aborts before anything is
# exposed to the internet if migrations or tests fail.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "No .env found. Run ./finalize_prod.sh first."; exit 1; }
if grep -qE '^[A-Z_]+=(replace-with|change-me)' .env; then
  echo ".env still contains placeholder secrets. Run ./finalize_prod.sh first."; exit 1
fi
DC="docker compose"

echo "== Build images =="
$DC build

echo "== Start data stores =="
$DC up -d postgres redis
$DC exec -T postgres sh -c 'until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; do sleep 1; done'

echo "== Ensure test database exists (older volumes pre-date the init script) =="
$DC exec -T postgres sh -c '
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT 1 FROM pg_database WHERE datname='"'"'starkeven_test'"'"'" | grep -q 1 \
  || psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE starkeven_test"'

echo "== Database migrations =="
$DC run --rm api alembic upgrade head
if ! $DC run --rm api alembic check >/dev/null 2>&1; then
  echo "Models differ from the migrated schema; generating a 'sync_schema' migration..."
  $DC run --rm --user "$(id -u):$(id -g)" -v "$PWD/alembic/versions:/app/alembic/versions" \
    api alembic revision --autogenerate -m sync_schema
  $DC run --rm -v "$PWD/alembic/versions:/app/alembic/versions" api alembic upgrade head
  echo "NOTE: review and commit the new file in alembic/versions/."
fi

echo "== Test suite (must pass before going live) =="
$DC run --rm api pytest -q

echo "== Go live =="
$DC up -d
echo "Waiting for the API to report healthy..."
for _ in $(seq 1 40); do
  if [ "$($DC ps --format '{{.Health}}' api 2>/dev/null | head -1)" = "healthy" ]; then
    echo "API healthy."; $DC ps; exit 0
  fi
  sleep 3
done
echo "API did not become healthy. Logs:"; $DC logs --tail=80 api; exit 1
