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
