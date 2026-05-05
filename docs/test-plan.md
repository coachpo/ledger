# Test Plan

> Status: Live automated-coverage reference as of 2026-05-05 (`a8ad8fb`).

## Backend Quality Gates

- `uv run ruff check app tests`
- `uv run black --check app tests`
- `uv run isort --check-only app tests`
- `uv run mypy app`
- `uv run pytest`

Backend tests cover preserved `/api/v1` CRUD, templates, reports, manifest parsing, model connections, MCP runtime behavior, native runtime tools, memory reports, platform runs, DB upgrades, and removed-route guarantees.

## Frontend Quality Gates

- `pnpm lint`
- `pnpm typecheck`
- `pnpm build`
- `pnpm test:run`
- `pnpm test:e2e`

Frontend tests cover API helpers, query keys, formatting helpers, markdown formatting, portfolio analytics, platform authoring helpers, routed platform editors, and browser E2E route families.

## E2E Scope

Playwright uses Chromium only. `frontend/playwright.config.ts` starts a dedicated backend on `8001` and built frontend preview on `4173`.

The backend helper runs `uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8001` and defaults `QUOTE_PROVIDER_BACKEND=deterministic`. The frontend helper builds first, previews with `--strictPort`, and defaults `VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1`.

Specs use API-assisted setup when it keeps UI assertions focused. Preserved product setup uses `/api/v1`; platform setup uses `/api`.

Route-family coverage includes smoke/navigation, portfolio CRUD, reports/templates, model connections, capabilities, MCP servers, agents/runs, output schemas, workflows/runs, and run detail fixtures. Removed-route assertions cover `/skills*`, `/templates/seed`, and legacy navigation entries.
