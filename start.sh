#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_VENV="$BACKEND_DIR/.venv"

export POSTGRES_DB="${POSTGRES_DB:-ledger}"
export POSTGRES_USER="${POSTGRES_USER:-ledger}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ledger}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_PORT}/${POSTGRES_DB}}"
export STORAGE_DIR="${STORAGE_DIR:-$BACKEND_DIR/storage}"
export RAW_STORAGE_DIR="${RAW_STORAGE_DIR:-$BACKEND_DIR/storage/raw}"
export VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://127.0.0.1:8000/api}"

if ! command -v docker >/dev/null 2>&1; then
  printf 'Docker is required to provision PostgreSQL for local development.\n' >&2
  exit 1
fi

if ! command -v pnpm >/dev/null 2>&1; then
  printf 'pnpm is required to run the frontend dev server.\n' >&2
  exit 1
fi

kill_port_listener() {
  local port="$1"
  local pids

  if ! command -v lsof >/dev/null 2>&1; then
    return
  fi

  pids="$(lsof -ti TCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return
  fi

  printf 'Stopping existing listener(s) on port %s: %s\n' "$port" "$pids"
  kill $pids >/dev/null 2>&1 || true

  for _ in {1..10}; do
    if ! lsof -ti TCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done

  pids="$(lsof -ti TCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    printf 'Force stopping listener(s) on port %s: %s\n' "$port" "$pids"
    kill -9 $pids >/dev/null 2>&1 || true
  fi
}

stop_existing_instances() {
  docker compose stop postgres >/dev/null 2>&1 || true
  kill_port_listener "$POSTGRES_PORT"
  kill_port_listener 8000
  kill_port_listener 5173
}

python3 -m venv "$BACKEND_VENV"
"$BACKEND_VENV/bin/pip" install -e "$BACKEND_DIR[dev]"

pnpm install --dir "$FRONTEND_DIR"

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

mkdir -p "$RAW_STORAGE_DIR"

stop_existing_instances

docker compose up -d postgres

POSTGRES_CONTAINER_ID="$(docker compose ps -q postgres)"
if [[ -z "$POSTGRES_CONTAINER_ID" ]]; then
  printf 'Failed to resolve PostgreSQL container ID.\n' >&2
  exit 1
fi

for attempt in {1..30}; do
  POSTGRES_HEALTH="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$POSTGRES_CONTAINER_ID" 2>/dev/null || true)"
  if [[ "$POSTGRES_HEALTH" == "healthy" ]]; then
    break
  fi
  if [[ "$attempt" -eq 30 ]]; then
    printf 'PostgreSQL did not become healthy in time.\n' >&2
    docker compose logs postgres >&2 || true
    exit 1
  fi
  sleep 2
done

if ! docker compose exec -T postgres psql -U "$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${POSTGRES_DB}'" | grep -q 1; then
  docker compose exec -T postgres createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
fi

(
  cd "$BACKEND_DIR"
  "$BACKEND_VENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

(
  cd "$FRONTEND_DIR"
  pnpm vite --host 127.0.0.1 --port 5173
) &
FRONTEND_PID=$!

printf 'Database: http://127.0.0.1:%s (%s)\n' "$POSTGRES_PORT" "$POSTGRES_DB"
printf 'Backend:  http://127.0.0.1:8000\n'
printf 'Frontend: http://127.0.0.1:5173\n'

wait "$BACKEND_PID" "$FRONTEND_PID"
