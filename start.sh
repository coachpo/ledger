#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
API_BASE_URL="${VITE_API_BASE_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}/api/v1}"
DEFAULT_DATABASE_URL="postgresql+psycopg://ledger:ledger@localhost:25432/ledger"
DATABASE_URL="${DATABASE_URL:-}"
DB_IMAGE="${LEDGER_DB_IMAGE:-postgres:16-alpine}"
DB_CONTAINER_NAME="${LEDGER_DB_CONTAINER_NAME:-}"
DB_VOLUME_NAME="${LEDGER_DB_VOLUME_NAME:-}"

PYTHON_BIN=""

for candidate in python3 python; do
  if ! command -v "$candidate" >/dev/null 2>&1; then
    continue
  fi

  if "$candidate" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi

  if [[ -z "$PYTHON_BIN" ]]; then
    PYTHON_BIN="$candidate"
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  printf 'Python is required but was not found.\n' >&2
  exit 1
fi

if ! command -v pnpm >/dev/null 2>&1; then
  printf 'pnpm is required but was not found.\n' >&2
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  printf 'Frontend dependencies are missing. Run: (cd "%s" && pnpm install)\n' "$FRONTEND_DIR" >&2
  exit 1
fi

if ! (cd "$BACKEND_DIR" && "$PYTHON_BIN" -c "import fastapi, uvicorn" >/dev/null 2>&1); then
  printf "Backend dependencies are missing. Run: %s -m pip install -e './backend[dev]'\n" "$PYTHON_BIN" >&2
  exit 1
fi

read_backend_env_value() {
  local key=$1
  local env_file="$BACKEND_DIR/.env"

  if [[ ! -f "$env_file" ]]; then
    return 1
  fi

  "$PYTHON_BIN" - "$env_file" "$key" <<'PY'
from pathlib import Path
import sys

env_file, key = sys.argv[1], sys.argv[2]

for raw_line in Path(env_file).read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue

    current_key, value = line.split("=", 1)
    if current_key.strip() == key:
        print(value.strip().strip('"').strip("'"))
        raise SystemExit(0)

raise SystemExit(1)
PY
}

resolve_backend_database_url() {
  local env_database_url=""

  if [[ -n "$DATABASE_URL" ]]; then
    printf '%s' "$DATABASE_URL"
    return
  fi

  if env_database_url="$(read_backend_env_value DATABASE_URL 2>/dev/null)"; then
    printf '%s' "$env_database_url"
    return
  fi

  printf '%s' "$DEFAULT_DATABASE_URL"
}

DATABASE_URL="$(resolve_backend_database_url)"

eval "$($PYTHON_BIN - "$DATABASE_URL" <<'PY'
from urllib.parse import unquote, urlsplit
import shlex
import sys

database_url = sys.argv[1]
parts = urlsplit(database_url)

values = {
    "DB_SCHEME": parts.scheme.split("+", 1)[0],
    "DB_HOST": parts.hostname or "",
    "DB_PORT": str(parts.port or 5432),
    "DB_USER": unquote(parts.username or ""),
    "DB_PASSWORD": unquote(parts.password or ""),
    "DB_NAME": parts.path.lstrip("/"),
}

for key, value in values.items():
    print(f"{key}={shlex.quote(value)}")
PY
)"

if [[ "$DB_SCHEME" != "postgres" && "$DB_SCHEME" != "postgresql" ]]; then
  printf 'DATABASE_URL must use PostgreSQL: %s\n' "$DATABASE_URL" >&2
  exit 1
fi

if [[ -z "$DB_HOST" || -z "$DB_NAME" ]]; then
  printf 'DATABASE_URL is missing required connection parts: %s\n' "$DATABASE_URL" >&2
  exit 1
fi

if [[ -z "$DB_CONTAINER_NAME" ]]; then
  DB_CONTAINER_NAME="ledger-postgres-${DB_PORT}"
fi

if [[ -z "$DB_VOLUME_NAME" ]]; then
  DB_VOLUME_NAME="ledger-postgres-data-${DB_PORT}"
fi

database_started=0
backend_pid=""
frontend_pid=""
backend_started=0
frontend_started=0

port_is_listening() {
  local port=$1
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

probe_host() {
  local host=$1
  if [[ "$host" == "0.0.0.0" ]]; then
    printf '127.0.0.1'
    return
  fi

  printf '%s' "$host"
}

database_uses_local_host() {
  case "$DB_HOST" in
    localhost|127.0.0.1|0.0.0.0)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

docker_container_exists() {
  local container_name=$1
  docker container inspect "$container_name" >/dev/null 2>&1
}

docker_container_running() {
  local container_name=$1
  [[ "$(docker container inspect -f '{{.State.Running}}' "$container_name" 2>/dev/null)" == "true" ]]
}

wait_for_database_container() {
  local deadline=$((SECONDS + 60))

  while (( SECONDS < deadline )); do
    if ! docker_container_running "$DB_CONTAINER_NAME"; then
      return 1
    fi

    if docker exec "$DB_CONTAINER_NAME" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
      return 0
    fi

    sleep 2
  done

  return 1
}

ensure_database_ready() {
  if ! database_uses_local_host; then
    printf 'Using external database on %s:%s\n' "$DB_HOST" "$DB_PORT"
    return
  fi

  if port_is_listening "$DB_PORT"; then
    printf 'Reusing existing database on %s:%s\n' "$DB_HOST" "$DB_PORT"
    return
  fi

  if [[ -z "$DB_USER" || -z "$DB_PASSWORD" || -z "$DB_NAME" ]]; then
    printf 'Cannot provision the local database without user, password, and database name in DATABASE_URL.\n' >&2
    exit 1
  fi

  if ! command -v docker >/dev/null 2>&1; then
    printf 'Docker is required to start the local database but was not found.\n' >&2
    exit 1
  fi

  if ! docker info >/dev/null 2>&1; then
    printf 'Docker is installed but the daemon is not available.\n' >&2
    exit 1
  fi

  printf 'Starting database container %s on %s:%s\n' "$DB_CONTAINER_NAME" "$DB_HOST" "$DB_PORT"

  if docker_container_exists "$DB_CONTAINER_NAME"; then
    docker start "$DB_CONTAINER_NAME" >/dev/null
  else
    docker run -d \
      --name "$DB_CONTAINER_NAME" \
      --publish "${DB_PORT}:5432" \
      --env "POSTGRES_DB=$DB_NAME" \
      --env "POSTGRES_USER=$DB_USER" \
      --env "POSTGRES_PASSWORD=$DB_PASSWORD" \
      --volume "${DB_VOLUME_NAME}:/var/lib/postgresql/data" \
      --health-cmd "pg_isready -U $DB_USER -d $DB_NAME" \
      --health-interval 5s \
      --health-timeout 5s \
      --health-retries 10 \
      "$DB_IMAGE" >/dev/null
  fi

  database_started=1

  if ! wait_for_database_container; then
    printf 'Database container %s failed to become ready.\n' "$DB_CONTAINER_NAME" >&2
    docker logs "$DB_CONTAINER_NAME" >&2 || true
    exit 1
  fi
}

stop_database_container() {
  if [[ "$database_started" -eq 1 ]]; then
    docker stop "$DB_CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
}

ledger_backend_running() {
  local host=$1
  local port=$2
  local resolved_host

  resolved_host="$(probe_host "$host")"

  "$PYTHON_BIN" - "$resolved_host" "$port" <<'PY' >/dev/null 2>&1
import json
import sys
import urllib.request

host, port = sys.argv[1], sys.argv[2]
url = f"http://{host}:{port}/health"

try:
    with urllib.request.urlopen(url, timeout=2) as response:
        payload = json.load(response)
except Exception:
    raise SystemExit(1)

raise SystemExit(0 if payload == {"status": "ok"} else 1)
PY
}

kill_child_processes() {
  local signal=$1
  local pid=$2

  if ! command -v pkill >/dev/null 2>&1; then
    return
  fi

  pkill "-$signal" -P "$pid" 2>/dev/null || true
}

stop_process() {
  local pid=$1
  local deadline

  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    return
  fi

  kill_child_processes TERM "$pid"
  kill "$pid" 2>/dev/null || true

  deadline=$((SECONDS + 5))
  while kill -0 "$pid" 2>/dev/null && (( SECONDS < deadline )); do
    sleep 0.1
  done

  if kill -0 "$pid" 2>/dev/null; then
    kill_child_processes KILL "$pid"
    kill -KILL "$pid" 2>/dev/null || true
  fi

  wait "$pid" 2>/dev/null || true
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  if [[ "$frontend_started" -eq 1 ]]; then
    stop_process "$frontend_pid"
  fi

  if [[ "$backend_started" -eq 1 ]]; then
    stop_process "$backend_pid"
  fi

  stop_database_container

  exit "$exit_code"
}

trap cleanup EXIT INT TERM

if port_is_listening "$FRONTEND_PORT"; then
  printf 'Frontend port %s is already in use. Stop the existing process or run with FRONTEND_PORT=<port> ./start.sh\n' "$FRONTEND_PORT" >&2
  exit 1
fi

if port_is_listening "$BACKEND_PORT"; then
  if ledger_backend_running "$BACKEND_HOST" "$BACKEND_PORT"; then
    printf 'Reusing existing backend on http://%s:%s\n' "$BACKEND_HOST" "$BACKEND_PORT"
  else
    printf 'Backend port %s is already in use by another process. Stop it or run with BACKEND_PORT=<port> ./start.sh\n' "$BACKEND_PORT" >&2
    exit 1
  fi
else
  ensure_database_ready
  printf 'Starting backend on http://%s:%s\n' "$BACKEND_HOST" "$BACKEND_PORT"
  (
    cd "$BACKEND_DIR"
    exec "$PYTHON_BIN" -m uvicorn app.main:app --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT"
  ) &
  backend_pid=$!
  backend_started=1
fi

printf 'Starting frontend on http://%s:%s\n' "$FRONTEND_HOST" "$FRONTEND_PORT"
(
  cd "$FRONTEND_DIR"
  export VITE_API_BASE_URL="$API_BASE_URL"
  exec pnpm dev --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
) &
frontend_pid=$!
frontend_started=1

printf 'Frontend API base URL: %s\n' "$API_BASE_URL"
printf 'Press Ctrl+C to stop both services.\n'

status=0

while true; do
  if [[ "$backend_started" -eq 1 ]] && ! kill -0 "$backend_pid" 2>/dev/null; then
    wait "$backend_pid" || status=$?
    printf 'Backend exited. Stopping frontend...\n' >&2
    break
  fi

  if ! kill -0 "$frontend_pid" 2>/dev/null; then
    wait "$frontend_pid" || status=$?
    printf 'Frontend exited. Stopping backend...\n' >&2
    break
  fi

  sleep 1
done

exit "$status"
