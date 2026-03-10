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

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
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

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  if [[ -n "$frontend_pid" ]] && kill -0 "$frontend_pid" 2>/dev/null; then
    kill "$frontend_pid" 2>/dev/null || true
    wait "$frontend_pid" 2>/dev/null || true
  fi

  if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" 2>/dev/null; then
    kill "$backend_pid" 2>/dev/null || true
    wait "$backend_pid" 2>/dev/null || true
  fi

  exit "$exit_code"
}

trap cleanup EXIT INT TERM

printf 'Starting backend on http://%s:%s\n' "$BACKEND_HOST" "$BACKEND_PORT"
(
  cd "$BACKEND_DIR"
  exec "$PYTHON_BIN" -m uvicorn app.main:app --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT"
) &
backend_pid=$!

printf 'Starting frontend on http://%s:%s\n' "$FRONTEND_HOST" "$FRONTEND_PORT"
(
  cd "$FRONTEND_DIR"
  export VITE_API_BASE_URL="$API_BASE_URL"
  exec pnpm dev --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
) &
frontend_pid=$!

printf 'Frontend API base URL: %s\n' "$API_BASE_URL"
printf 'Press Ctrl+C to stop both services.\n'

status=0

while true; do
  if ! kill -0 "$backend_pid" 2>/dev/null; then
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
