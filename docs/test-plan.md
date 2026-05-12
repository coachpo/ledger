# Test Plan

> Status: Live automated-coverage reference for branch `main` at `10063aa`.

## Backend Quality Gates

- `uv run ruff check app tests`
- `uv run black --check app tests`
- `uv run isort --check-only app tests`
- `uv run mypy app`
- `uv run pytest`

Backend tests cover preserved `/api/v1` CRUD, templates, reports, workflow package manifests, package import/export with inline private MCP `env`, `headers`, and `query` values, model connections, global tools, package runtime behavior, native runtime tools, memory reports, trace metadata, global runs, DB upgrades, and removed-route guarantees.

## Frontend Quality Gates

- `pnpm lint`
- `pnpm typecheck`
- `pnpm build`
- `pnpm test:run`
- `pnpm test:e2e`

Frontend tests cover API helpers, query keys, formatting helpers, markdown formatting, portfolio analytics, workflow package helpers, package editor flows, layout routing, and browser E2E route families.

## E2E Scope

Playwright uses Chromium only. `frontend/playwright.config.ts` starts a dedicated backend on `8001` and built frontend preview on `4173`.

The backend helper runs `uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8001` and defaults `QUOTE_PROVIDER_BACKEND=deterministic`. The frontend helper builds first, previews with `--strictPort`, and defaults `VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1`.

Specs use API-assisted setup when it keeps UI assertions focused. Preserved product setup uses `/api/v1`; platform setup uses `/api`.

Route-family coverage includes smoke/navigation, portfolio CRUD, reports/templates, Workflow Packages, Model Connections, Runs, run detail fixtures, package import/export/preflight/launch flows, and the TradingAgents smoke package as ordinary demo data. Removed-route assertions cover `/skills*`, `/templates/seed`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, `/workflows*`, and legacy navigation entries.
