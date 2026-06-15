#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
APP_PORT="${APP_PORT:-8080}"
APP_URL="http://localhost:${APP_PORT}"

require_command() {
  local command_name="$1"

  if command -v "$command_name" >/dev/null 2>&1; then
    return 0
  fi

  printf 'Missing required command: %s.\n' "$command_name" >&2
  exit 1
}

require_command docker

if ! docker compose version >/dev/null 2>&1; then
  printf 'Docker Compose v2 is required but `docker compose` is unavailable.\n' >&2
  exit 1
fi

cd "$ROOT_DIR"

printf 'Starting SignalDeck local Docker Compose stack.\n'
printf 'App URL: %s\n' "$APP_URL"
printf 'Building latest local source and streaming logs. Press Ctrl+C to stop.\n'

exec docker compose -f "$COMPOSE_FILE" up --build --remove-orphans
