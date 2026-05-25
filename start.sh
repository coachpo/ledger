#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
REQUESTED_BACKEND_PORT="${BACKEND_PORT:-28000}"
SELECTED_BACKEND_PORT="$REQUESTED_BACKEND_PORT"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
REQUESTED_FRONTEND_PORT="${FRONTEND_PORT:-25173}"
SELECTED_FRONTEND_PORT="$REQUESTED_FRONTEND_PORT"

is_port_listening() {
  lsof -tiTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

first_available_port() {
  local candidate

  for candidate in "$@"; do
    if ! is_port_listening "$candidate"; then
      printf '%s' "$candidate"
      return 0
    fi
  done

  return 1
}

require_command() {
  local command_name="$1"
  local install_hint="${2:-}"

  if command -v "$command_name" >/dev/null 2>&1; then
    return 0
  fi

  printf 'Missing required command: %s.\n' "$command_name" >&2
  if [[ -n "$install_hint" ]]; then
    printf '%s\n' "$install_hint" >&2
  fi
  exit 1
}

require_frontend_dependencies() {
  if (
    cd "$FRONTEND_DIR"
    pnpm exec vite --version >/dev/null 2>&1
  ); then
    return 0
  fi

  printf 'Frontend dependencies are not installed.\n' >&2
  printf 'Run (cd "%s" && pnpm install) and retry.\n' "$FRONTEND_DIR" >&2
  exit 1
}

validate_local_requirements() {
  require_command lsof 'Install lsof and retry.'
  require_command uv 'Install uv and retry.'
  require_command pnpm 'Install pnpm 10+ and retry.'

  if [[ -z "${DATABASE_URL:-}" ]]; then
    require_command docker 'Install Docker with docker compose support or set DATABASE_URL explicitly.'
    if ! docker compose version >/dev/null 2>&1; then
      printf 'Docker Compose is required but `docker compose` is unavailable.\n' >&2
      exit 1
    fi
  fi

  require_frontend_dependencies
}

normalize_loopback_aliases() {
  local host="$1"

  case "$host" in
    127.0.0.1)
      printf '%s\n%s\n' '127.0.0.1' 'localhost'
      ;;
    localhost)
      printf '%s\n%s\n' 'localhost' '127.0.0.1'
      ;;
    *)
      printf '%s\n' "$host"
      ;;
  esac
}

append_unique_origin() {
  local origins="$1"
  local origin="$2"
  local wrapped_origins=",${origins},"

  if [[ "$wrapped_origins" == *",${origin},"* ]]; then
    printf '%s' "$origins"
  elif [[ -z "$origins" ]]; then
    printf '%s' "$origin"
  else
    printf '%s,%s' "$origins" "$origin"
  fi
}

merged_cors_allowed_origins() {
  local frontend_host="$1"
  local frontend_port="$2"
  local allowed_origins="${CORS_ALLOWED_ORIGINS:-}"
  local host

  while IFS= read -r host; do
    [[ -z "$host" ]] && continue
    allowed_origins="$(append_unique_origin "$allowed_origins" "http://${host}:${frontend_port}")"
  done < <(normalize_loopback_aliases "$frontend_host")

  printf '%s' "$allowed_origins"
}

kill_listener_on_port() {
  local port="$1"
  local pids
  local pid

  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return 0
  fi

  printf 'Stopping process(es) listening on port %s.\n' "$port"
  for pid in $pids; do
    kill "$pid" 2>/dev/null || true
  done

  for _ in {1..10}; do
    if ! is_port_listening "$port"; then
      return 0
    fi

    sleep 1
  done

  if is_port_listening "$port"; then
    printf 'Force-stopping process(es) still listening on port %s.\n' "$port"
    for pid in $pids; do
      kill -9 "$pid" 2>/dev/null || true
    done
  fi
}

stop_local_database() {
  printf 'Stopping local SignalDeck database container, if running.\n'
  (
    cd "$BACKEND_DIR"
    docker compose down --remove-orphans >/dev/null 2>&1 || true
  )
}

stop_existing_scheduler_workers() {
  local pids
  local pid

  if ! command -v pgrep >/dev/null 2>&1; then
    return 0
  fi

  pids="$(pgrep -f 'app.workers.run_scheduler' 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return 0
  fi

  printf 'Stopping existing SignalDeck scheduler worker(s).\n'
  for pid in $pids; do
    kill "$pid" 2>/dev/null || true
  done
}

stop_existing_instances() {
  local port

  printf 'Stopping existing SignalDeck development instances.\n'
  stop_local_database
  stop_existing_scheduler_workers

  for port in "$REQUESTED_BACKEND_PORT" 28000 28001 28002 "$REQUESTED_FRONTEND_PORT" 25173 25174; do
    kill_listener_on_port "$port"
  done
}

wait_for_database() {
  local database_url="$1"

  (
    cd "$BACKEND_DIR"
    DATABASE_URL="$database_url" uv run python - <<'PY'
from sqlalchemy import create_engine, text
import os

engine = create_engine(
    os.environ["DATABASE_URL"],
    future=True,
    connect_args={"connect_timeout": 2},
)
with engine.connect() as connection:
    connection.execute(text("SELECT 1"))
PY
  ) >/dev/null 2>&1
}

database_url_for_port() {
  printf 'postgresql+psycopg://signaldeck:signaldeck@localhost:%s/signaldeck' "$1"
}

validate_local_requirements
stop_existing_instances

if [[ -z "${FRONTEND_PORT:-}" ]]; then
  if is_port_listening "$SELECTED_FRONTEND_PORT"; then
    if is_port_listening 25174; then
      printf 'Frontend ports 25173 and 25174 are both in use; stop one or set FRONTEND_PORT explicitly.\n' >&2
      exit 1
    fi

    printf 'Port %s is in use; switching frontend to 25174 so backend CORS stays valid.\n' "$SELECTED_FRONTEND_PORT"
    SELECTED_FRONTEND_PORT=25174
  fi
fi

if is_port_listening "$SELECTED_BACKEND_PORT"; then
  if [[ -z "${BACKEND_PORT:-}" ]]; then
    fallback_backend_port="$(first_available_port 28001 28002 || true)"

    if [[ -z "$fallback_backend_port" ]]; then
      printf 'Backend port %s is still occupied after cleanup and no fallback backend port is available.\n' "$SELECTED_BACKEND_PORT" >&2
      exit 1
    fi

    printf 'Backend port %s is still occupied after cleanup; switching backend to %s.\n' "$SELECTED_BACKEND_PORT" "$fallback_backend_port"
    SELECTED_BACKEND_PORT="$fallback_backend_port"
  else
    printf 'Configured backend port %s is still occupied after cleanup.\n' "$SELECTED_BACKEND_PORT" >&2
    exit 1
  fi
fi

REUSE_BACKEND=0

API_BASE_URL="${VITE_API_BASE_URL:-http://${BACKEND_HOST}:${SELECTED_BACKEND_PORT}/api/v1}"

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

if [[ "$REUSE_BACKEND" -eq 0 ]]; then
  (
    cd "$BACKEND_DIR"

    selected_database_url="${DATABASE_URL:-$(database_url_for_port 25432)}"
    selected_db_port=25432
    should_start_local_db=0

    if [[ -z "${DATABASE_URL:-}" ]]; then
      if wait_for_database "$selected_database_url"; then
        printf 'Using existing PostgreSQL endpoint at %s.\n' "$selected_database_url"
      elif is_port_listening 25432; then
        fallback_db_port="$(first_available_port 25433 25434 || true)"

        if [[ -z "$fallback_db_port" ]]; then
          printf 'Port 25432 is unavailable and no fallback database port is available.\n' >&2
          exit 1
        fi

        selected_db_port="$fallback_db_port"
        selected_database_url="$(database_url_for_port "$selected_db_port")"
        should_start_local_db=1
        printf 'Port 25432 is unavailable or not a reachable PostgreSQL endpoint; starting local database on %s.\n' "$selected_db_port"
      else
        should_start_local_db=1
        printf 'Starting local database on %s.\n' "$selected_db_port"
      fi
    else
      printf 'Using DATABASE_URL from the environment.\n'
    fi

    if [[ "$should_start_local_db" -eq 1 ]]; then
      SIGNALDECK_DB_PORT="$selected_db_port" docker compose up -d db
    fi

    for _ in {1..30}; do
      if wait_for_database "$selected_database_url"; then
        break
      fi

      sleep 1
    done

    if ! wait_for_database "$selected_database_url"; then
      printf 'Database did not become ready at %s.\n' "$selected_database_url" >&2
      exit 1
    fi

    cleanup_backend_children() {
      if [[ -n "${SCHEDULER_PID:-}" ]]; then
        kill "$SCHEDULER_PID" 2>/dev/null || true
        wait "$SCHEDULER_PID" 2>/dev/null || true
      fi
    }

    trap cleanup_backend_children EXIT INT TERM

    printf 'Starting SignalDeck scheduler worker.\n'
    DATABASE_URL="$selected_database_url" uv run python -m app.workers.run_scheduler &
    SCHEDULER_PID=$!

    BACKEND_CORS_ALLOWED_ORIGINS="$(merged_cors_allowed_origins "$FRONTEND_HOST" "$SELECTED_FRONTEND_PORT")"
    DATABASE_URL="$selected_database_url" CORS_ALLOWED_ORIGINS="$BACKEND_CORS_ALLOWED_ORIGINS" uv run uvicorn app.main:app --reload --host "$BACKEND_HOST" --port "$SELECTED_BACKEND_PORT"
  ) &
BACKEND_PID=$!
fi

cd "$FRONTEND_DIR"
VITE_API_BASE_URL="$API_BASE_URL" pnpm dev --host "$FRONTEND_HOST" --port "$SELECTED_FRONTEND_PORT"
