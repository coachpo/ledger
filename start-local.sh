#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

APP_PORT="${APP_PORT:-8080}"
BACKEND_HOST="127.0.0.1"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="127.0.0.1"
FRONTEND_PORT="${FRONTEND_PORT:-$APP_PORT}"
RUN_SCHEDULER="${RUN_SCHEDULER:-true}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-signaldeck}"
DEFAULT_DATABASE_URL="postgresql+psycopg://signaldeck:${POSTGRES_PASSWORD}@localhost:25432/signaldeck"
LOCAL_POSTGRES_CONTAINER="signaldeck-local-postgres"
LOCAL_POSTGRES_IMAGE="pgvector/pgvector:pg16"
LOCAL_POSTGRES_PORT="25432"
LOCAL_POSTGRES_VOLUME="signaldeck-postgres-data"

export DATABASE_URL="${DATABASE_URL:-$DEFAULT_DATABASE_URL}"
export AGENT_PLATFORM_ENCRYPTION_KEY="${AGENT_PLATFORM_ENCRYPTION_KEY:-signaldeck-agent-platform-dev-key}"
export SIGNALDECK_RUNTIME_MODE="${SIGNALDECK_RUNTIME_MODE:-local}"
export VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}/api/v1}"
export PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-http://localhost:${FRONTEND_PORT}}"
export CORS_ALLOWED_ORIGINS="${CORS_ALLOWED_ORIGINS:-http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}}"

LOG_DIR="$ROOT_DIR/.tmp/start-local/$(date +%Y%m%d-%H%M%S)"
BACKEND_LOG="$LOG_DIR/backend.log"
SCHEDULER_LOG="$LOG_DIR/scheduler.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

CHILD_PIDS=()
CHILD_LABELS=()
CHILD_LOGS=()
MANAGED_DATABASE_STARTED=false
STOPPING=false

status() {
  printf '[start-local] %s\n' "$*"
}

die() {
  printf '[start-local] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  local command_name="$1"

  if command -v "$command_name" >/dev/null 2>&1; then
    return 0
  fi

  die "Missing required command: $command_name."
}

require_numeric_major_at_least() {
  local label="$1"
  local actual_version="$2"
  local minimum_major="$3"
  local major="${actual_version%%.*}"

  case "$major" in
    ''|*[!0-9]*)
      die "Could not parse $label version: $actual_version."
      ;;
  esac

  if (( major < minimum_major )); then
    die "$label $actual_version is unsupported; major version $minimum_major or newer is required."
  fi
}

validate_boolean() {
  case "$RUN_SCHEDULER" in
    true|TRUE|True|1|yes|YES|false|FALSE|False|0|no|NO)
      return 0
      ;;
    *)
      die "RUN_SCHEDULER must be true or false."
      ;;
  esac
}

scheduler_enabled() {
  case "$RUN_SCHEDULER" in
    true|TRUE|True|1|yes|YES)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

using_managed_local_database() {
  [[ "$DATABASE_URL" == "$DEFAULT_DATABASE_URL" ]]
}

docker_container_running() {
  local container_name="$1"

  [[ "$(docker inspect -f '{{.State.Running}}' "$container_name" 2>/dev/null || true)" == "true" ]]
}

docker_container_exists() {
  local container_name="$1"

  docker inspect "$container_name" >/dev/null 2>&1
}

port_listener_pids() {
  local port="$1"

  lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u || true
}

stop_port_listeners() {
  local port="$1"
  local label="$2"
  local pids=()
  local remaining_pids=()
  local deadline
  local pid

  mapfile -t pids < <(port_listener_pids "$port")
  if ((${#pids[@]} == 0)); then
    return 0
  fi

  status "Freeing $label port $port from listener pid(s): ${pids[*]}"
  for pid in "${pids[@]}"; do
    kill -TERM "$pid" >/dev/null 2>&1 || true
  done

  deadline=$((SECONDS + 5))
  while (( SECONDS < deadline )); do
    mapfile -t remaining_pids < <(port_listener_pids "$port")
    if ((${#remaining_pids[@]} == 0)); then
      return 0
    fi
    sleep 1
  done

  mapfile -t remaining_pids < <(port_listener_pids "$port")
  for pid in "${remaining_pids[@]}"; do
    status "Force-stopping $label listener pid $pid on port $port."
    kill -KILL "$pid" >/dev/null 2>&1 || true
  done

  sleep 1
  mapfile -t remaining_pids < <(port_listener_pids "$port")
  if ((${#remaining_pids[@]} > 0)); then
    die "Could not free $label port $port; listener pid(s) remain: ${remaining_pids[*]}"
  fi
}

free_application_ports() {
  local seen_ports=" "
  local port

  for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    if [[ "$seen_ports" == *" $port "* ]]; then
      continue
    fi
    seen_ports+="$port "
    stop_port_listeners "$port" "application"
  done
}

show_log_tail() {
  local log_file="$1"

  if [[ -f "$log_file" ]]; then
    printf '[start-local] Last 30 lines from %s:\n' "$log_file" >&2
    tail -n 30 "$log_file" >&2 || true
  fi
}

stop_managed_database() {
  if [[ "$MANAGED_DATABASE_STARTED" != "true" ]]; then
    return 0
  fi

  status "Stopping local PostgreSQL container $LOCAL_POSTGRES_CONTAINER."
  docker stop "$LOCAL_POSTGRES_CONTAINER" >/dev/null 2>&1 || true
  MANAGED_DATABASE_STARTED=false
}

stop_children() {
  if [[ "$STOPPING" == "true" ]]; then
    return 0
  fi
  STOPPING=true
  trap - EXIT

  if ((${#CHILD_PIDS[@]} == 0)); then
    stop_managed_database
    return 0
  fi

  status "Stopping child processes..."
  for ((idx = ${#CHILD_PIDS[@]} - 1; idx >= 0; idx--)); do
    local pid="${CHILD_PIDS[$idx]}"
    local label="${CHILD_LABELS[$idx]}"
    status "Stopping $label (pid $pid)."
    kill -TERM "-$pid" >/dev/null 2>&1 || true
  done

  local deadline=$((SECONDS + 10))
  local all_stopped=false
  while (( SECONDS < deadline )); do
    all_stopped=true
    for pid in "${CHILD_PIDS[@]}"; do
      if kill -0 "$pid" >/dev/null 2>&1; then
        all_stopped=false
        break
      fi
    done
    [[ "$all_stopped" == "true" ]] && break
    sleep 1
  done

  if [[ "$all_stopped" != "true" ]]; then
    for pid in "${CHILD_PIDS[@]}"; do
      kill -KILL "-$pid" >/dev/null 2>&1 || true
    done
  fi

  for pid in "${CHILD_PIDS[@]}"; do
    wait "$pid" >/dev/null 2>&1 || true
  done

  stop_managed_database
}

on_interrupt() {
  printf '\n'
  status "Interrupted; shutting down SignalDeck local stack."
  stop_children
  exit 130
}

on_terminate() {
  status "Terminated; shutting down SignalDeck local stack."
  stop_children
  exit 143
}

start_child() {
  local label="$1"
  local log_file="$2"
  local cwd="$3"
  shift 3

  status "Starting $label..."
  setsid bash -c 'cd "$1" && shift && exec "$@"' _ "$cwd" "$@" >"$log_file" 2>&1 &
  local pid=$!
  CHILD_PIDS+=("$pid")
  CHILD_LABELS+=("$label")
  CHILD_LOGS+=("$log_file")
  status "$label pid=$pid log=$log_file"
}

ensure_children_running() {
  local pid label log_file exit_status

  for idx in "${!CHILD_PIDS[@]}"; do
    pid="${CHILD_PIDS[$idx]}"
    label="${CHILD_LABELS[$idx]}"
    log_file="${CHILD_LOGS[$idx]}"

    if kill -0 "$pid" >/dev/null 2>&1; then
      continue
    fi

    set +e
    wait "$pid"
    exit_status=$?
    set -e
    show_log_tail "$log_file"
    die "$label exited unexpectedly with status $exit_status."
  done
}

wait_for_http() {
  local label="$1"
  local url="$2"
  local timeout_seconds="$3"
  local deadline=$((SECONDS + timeout_seconds))

  status "Waiting for $label at $url."
  while (( SECONDS < deadline )); do
    ensure_children_running
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      status "$label is ready."
      return 0
    fi
    sleep 1
  done

  die "$label did not become ready within ${timeout_seconds}s: $url"
}

check_dependencies() {
  local node_version

  require_command bash
  require_command curl
  require_command lsof
  require_command node
  require_command pnpm
  require_command setsid
  require_command uv
  if using_managed_local_database; then
    require_command docker
  fi

  node_version="$(node --version)"
  require_numeric_major_at_least "Node" "${node_version#v}" 24
  require_numeric_major_at_least "pnpm" "$(pnpm --version)" 10
}

prepare_dependencies() {
  status "Preparing backend dependencies with uv sync --frozen."
  (cd "$BACKEND_DIR" && uv sync --frozen)

  status "Preparing frontend dependencies with pnpm install --frozen-lockfile."
  (cd "$FRONTEND_DIR" && pnpm install --frozen-lockfile)
}

wait_for_local_database() {
  local timeout_seconds="${1:-60}"
  local deadline=$((SECONDS + timeout_seconds))

  status "Waiting for local PostgreSQL at 127.0.0.1:${LOCAL_POSTGRES_PORT}."
  while (( SECONDS < deadline )); do
    if ! docker_container_running "$LOCAL_POSTGRES_CONTAINER"; then
      docker logs --tail 30 "$LOCAL_POSTGRES_CONTAINER" >&2 || true
      die "Local PostgreSQL container exited before becoming ready."
    fi

    if docker exec "$LOCAL_POSTGRES_CONTAINER" pg_isready -U signaldeck -d signaldeck >/dev/null 2>&1; then
      status "Local PostgreSQL is ready."
      return 0
    fi

    sleep 1
  done

  docker logs --tail 30 "$LOCAL_POSTGRES_CONTAINER" >&2 || true
  die "Local PostgreSQL did not become ready within ${timeout_seconds}s."
}

start_local_database() {
  if ! using_managed_local_database; then
    status "Using DATABASE_URL override; skipping managed local PostgreSQL startup."
    return 0
  fi

  if docker_container_running "$LOCAL_POSTGRES_CONTAINER"; then
    status "Local PostgreSQL container $LOCAL_POSTGRES_CONTAINER is already running."
    wait_for_local_database 60
    return 0
  fi

  stop_port_listeners "$LOCAL_POSTGRES_PORT" "local PostgreSQL"

  if docker_container_exists "$LOCAL_POSTGRES_CONTAINER"; then
    status "Starting existing local PostgreSQL container $LOCAL_POSTGRES_CONTAINER."
    docker start "$LOCAL_POSTGRES_CONTAINER" >/dev/null
  else
    status "Creating local PostgreSQL container $LOCAL_POSTGRES_CONTAINER."
    docker volume create "$LOCAL_POSTGRES_VOLUME" >/dev/null
    docker run -d \
      --name "$LOCAL_POSTGRES_CONTAINER" \
      --label io.signaldeck.support=local-demo-only \
      --label io.signaldeck.production-artifact=false \
      -e POSTGRES_DB=signaldeck \
      -e POSTGRES_USER=signaldeck \
      -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
      -p "127.0.0.1:${LOCAL_POSTGRES_PORT}:5432" \
      -v "${LOCAL_POSTGRES_VOLUME}:/var/lib/postgresql/data" \
      "$LOCAL_POSTGRES_IMAGE" >/dev/null
  fi

  MANAGED_DATABASE_STARTED=true
  wait_for_local_database 60
}

preflight_database() {
  status "Checking PostgreSQL database and startup schema."
  if (cd "$BACKEND_DIR" && uv run --frozen python - <<'PY'
from __future__ import annotations

import sys

from app.db.session import init_db

try:
    init_db()
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc
PY
  ); then
    status "Database preflight passed."
    return 0
  fi

  die "Database preflight failed. Start local PostgreSQL/pgvector and set DATABASE_URL, or provide a reachable database at the default localhost:25432 signaldeck URL."
}

print_startup_summary() {
  status "SignalDeck bare-metal local startup"
  status "Repo root: $ROOT_DIR"
  status "App URL: http://localhost:${FRONTEND_PORT}"
  status "Frontend listen URL: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
  status "Backend health URL: http://${BACKEND_HOST}:${BACKEND_PORT}/health"
  status "Backend readiness URL: http://${BACKEND_HOST}:${BACKEND_PORT}/ready"
  status "Frontend API base: $VITE_API_BASE_URL"
  status "Scheduler enabled: $RUN_SCHEDULER"
  status "Logs directory: $LOG_DIR"
}

monitor_children() {
  status "SignalDeck local stack is running. Press Ctrl+C to stop."
  while true; do
    ensure_children_running
    sleep 2
  done
}

main() {
  cd "$ROOT_DIR"
  mkdir -p "$LOG_DIR"

  trap stop_children EXIT
  trap on_interrupt INT
  trap on_terminate TERM

  validate_boolean
  check_dependencies
  prepare_dependencies
  start_local_database
  preflight_database
  free_application_ports
  print_startup_summary

  start_child "backend" "$BACKEND_LOG" "$BACKEND_DIR" \
    uv run --frozen uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
  wait_for_http "backend health" "http://${BACKEND_HOST}:${BACKEND_PORT}/health" 60
  wait_for_http "backend readiness" "http://${BACKEND_HOST}:${BACKEND_PORT}/ready" 60

  if scheduler_enabled; then
    start_child "scheduler" "$SCHEDULER_LOG" "$BACKEND_DIR" \
      uv run --frozen python -m app.workers.run_scheduler
    sleep 1
    ensure_children_running
  else
    status "Scheduler disabled by RUN_SCHEDULER=$RUN_SCHEDULER."
  fi

  start_child "frontend" "$FRONTEND_LOG" "$FRONTEND_DIR" \
    pnpm run dev --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" --strictPort
  wait_for_http "frontend" "http://${FRONTEND_HOST}:${FRONTEND_PORT}" 60

  monitor_children
}

main "$@"
