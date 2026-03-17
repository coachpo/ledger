#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
COMPOSE_FILE="$BACKEND_DIR/docker-compose.yml"
COMPOSE_PROJECT_NAME="${LEDGER_COMPOSE_PROJECT_NAME:-ledger-local}"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-28000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-25173}"
DB_HOST="127.0.0.1"
DB_PORT="25432"
DB_NAME="ledger"
DB_USER="ledger"
DB_PASSWORD="ledger"
DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

PYTHON_BIN=""
backend_pid=""
frontend_pid=""
database_started=0
backend_started=0
frontend_started=0

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

require_command() {
  local command_name=$1

  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf '%s is required but was not found.\n' "$command_name" >&2
    exit 1
  fi
}

require_command docker
require_command lsof
require_command pnpm

if ! docker info >/dev/null 2>&1; then
  printf 'Docker is installed but the daemon is not available.\n' >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  printf 'docker compose is required but not available.\n' >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  printf 'Expected Docker Compose file at %s\n' "$COMPOSE_FILE" >&2
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

probe_host() {
  local host=$1

  case "$host" in
    0.0.0.0|"")
      printf '127.0.0.1'
      ;;
    *)
      printf '%s' "$host"
      ;;
  esac
}

compose_cmd() {
  docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT_NAME" "$@"
}

port_is_listening() {
  local port=$1
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

port_pids() {
  local port=$1
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk '!seen[$0]++'
}

wait_for_port_release() {
  local port=$1
  local timeout_seconds=${2:-10}
  local deadline=$((SECONDS + timeout_seconds))

  while (( SECONDS < deadline )); do
    if ! port_is_listening "$port"; then
      return 0
    fi

    sleep 1
  done

  ! port_is_listening "$port"
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

stop_docker_containers_publishing_port() {
  local port=$1
  local docker_ps_output
  local container_ids=()
  local container_id

  docker_ps_output="$(docker ps --format '{{.ID}}\t{{.Ports}}' 2>/dev/null || true)"
  if [[ -z "$docker_ps_output" ]]; then
    return
  fi

  while IFS= read -r container_id; do
    [[ -z "$container_id" ]] && continue
    container_ids+=("$container_id")
  done < <(
    printf '%s\n' "$docker_ps_output" | "$PYTHON_BIN" -c '
import sys

target_port = sys.argv[1]

for raw_line in sys.stdin:
    line = raw_line.rstrip("\n")
    if not line:
        continue

    container_id, _, port_mappings = line.partition("\t")
    for mapping in [item.strip() for item in port_mappings.split(",") if item.strip()]:
        if f":{target_port}->" in mapping or mapping.startswith(f"{target_port}->"):
            print(container_id)
            break
' "$port"
  )

  if [[ "${#container_ids[@]}" -eq 0 ]]; then
    return
  fi

  printf 'Stopping Docker containers publishing port %s: %s\n' "$port" "${container_ids[*]}"
  docker stop "${container_ids[@]}" >/dev/null
}

kill_port_listeners() {
  local port=$1
  local pid
  local command_line

  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"

    if [[ "$command_line" == *"com.docker"* || "$command_line" == *"vpnkit"* ]]; then
      continue
    fi

    printf 'Stopping process %s on port %s\n' "$pid" "$port"
    stop_process "$pid"
  done < <(port_pids "$port")

  if ! wait_for_port_release "$port" 10; then
    printf 'Port %s is still in use after cleanup.\n' "$port" >&2
    exit 1
  fi
}

stop_existing_stack() {
  compose_cmd down --remove-orphans >/dev/null 2>&1 || true

  for port in "$DB_PORT" "$BACKEND_PORT" "$FRONTEND_PORT"; do
    stop_docker_containers_publishing_port "$port"
  done

  for port in "$DB_PORT" "$BACKEND_PORT" "$FRONTEND_PORT"; do
    kill_port_listeners "$port"
  done
}

database_container_id() {
  compose_cmd ps -q db 2>/dev/null | tail -n 1
}

wait_for_database_ready() {
  local deadline=$((SECONDS + 60))
  local container_id=""

  while (( SECONDS < deadline )); do
    container_id="$(database_container_id)"

    if [[ -n "$container_id" ]] && docker exec "$container_id" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
      return 0
    fi

    sleep 2
  done

  return 1
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

wait_for_backend_ready() {
  local deadline=$((SECONDS + 60))

  while (( SECONDS < deadline )); do
    if ledger_backend_running "$BACKEND_HOST" "$BACKEND_PORT"; then
      return 0
    fi

    if [[ "$backend_started" -eq 1 ]] && ! kill -0 "$backend_pid" 2>/dev/null; then
      return 1
    fi

    sleep 1
  done

  return 1
}

build_cors_allowed_origins() {
  local extra_origins=${CORS_ALLOWED_ORIGINS:-}

  "$PYTHON_BIN" - "$FRONTEND_HOST" "$FRONTEND_PORT" "$extra_origins" <<'PY'
import json
import sys

frontend_host, frontend_port, extra_origins = sys.argv[1], sys.argv[2], sys.argv[3]
origins: list[str] = []

if extra_origins.strip():
    parsed_extra_origins = None
    try:
        parsed_extra_origins = json.loads(extra_origins)
    except json.JSONDecodeError:
        parsed_extra_origins = [item.strip() for item in extra_origins.split(",") if item.strip()]

    if isinstance(parsed_extra_origins, list):
        extra_origin_values = [str(item).strip() for item in parsed_extra_origins if str(item).strip()]
    else:
        extra_origin_values = [str(parsed_extra_origins).strip()] if str(parsed_extra_origins).strip() else []

    for origin in extra_origin_values:
        if origin not in origins:
            origins.append(origin)

for candidate in (
    f"http://127.0.0.1:{frontend_port}",
    f"http://localhost:{frontend_port}",
):
    if candidate not in origins:
        origins.append(candidate)

if frontend_host not in {"", "0.0.0.0", "127.0.0.1", "localhost"}:
    candidate = f"http://{frontend_host}:{frontend_port}"
    if candidate not in origins:
        origins.append(candidate)

print(json.dumps(origins))
PY
}

stop_database() {
  if [[ "$database_started" -eq 1 ]]; then
    compose_cmd down --remove-orphans >/dev/null 2>&1 || true
  fi
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

  stop_database

  exit "$exit_code"
}

trap cleanup EXIT INT TERM

BACKEND_PUBLIC_HOST="$(probe_host "$BACKEND_HOST")"
API_BASE_URL="http://${BACKEND_PUBLIC_HOST}:${BACKEND_PORT}/api/v1"
RESOLVED_CORS_ALLOWED_ORIGINS="$(build_cors_allowed_origins)"

printf 'Cleaning up ports %s, %s, and %s before startup\n' "$DB_PORT" "$BACKEND_PORT" "$FRONTEND_PORT"
stop_existing_stack

printf 'Starting database on postgres://%s@%s:%s/%s\n' "$DB_USER" "$DB_HOST" "$DB_PORT" "$DB_NAME"
compose_cmd up -d db >/dev/null
database_started=1

if ! wait_for_database_ready; then
  printf 'Database failed to become ready.\n' >&2
  compose_cmd logs db >&2 || true
  exit 1
fi

printf 'Starting backend on http://%s:%s\n' "$BACKEND_PUBLIC_HOST" "$BACKEND_PORT"
(
  cd "$BACKEND_DIR"
  export DATABASE_URL="$DATABASE_URL"
  export CORS_ALLOWED_ORIGINS="$RESOLVED_CORS_ALLOWED_ORIGINS"
  exec "$PYTHON_BIN" -m uvicorn app.main:app --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT"
) &
backend_pid=$!
backend_started=1

if ! wait_for_backend_ready; then
  printf 'Backend failed to become ready on port %s.\n' "$BACKEND_PORT" >&2
  exit 1
fi

printf 'Starting frontend on http://%s:%s\n' "$(probe_host "$FRONTEND_HOST")" "$FRONTEND_PORT"
(
  cd "$FRONTEND_DIR"
  export VITE_API_BASE_URL="$API_BASE_URL"
  exec pnpm dev --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
) &
frontend_pid=$!
frontend_started=1

printf 'Frontend API base URL: %s\n' "$API_BASE_URL"
printf 'Press Ctrl+C to stop the database, backend, and frontend.\n'

status=0

while true; do
  if [[ "$backend_started" -eq 1 ]] && ! kill -0 "$backend_pid" 2>/dev/null; then
    wait "$backend_pid" || status=$?
    printf 'Backend exited. Stopping the rest of the stack...\n' >&2
    break
  fi

  if [[ "$frontend_started" -eq 1 ]] && ! kill -0 "$frontend_pid" 2>/dev/null; then
    wait "$frontend_pid" || status=$?
    printf 'Frontend exited. Stopping the rest of the stack...\n' >&2
    break
  fi

  sleep 1
done

exit "$status"
