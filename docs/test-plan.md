# Test Plan

> Status: Live automated-coverage reference as of 2026-05-04 (`b4ac445`).

## Backend Quality Gates

- `uv run ruff check app tests`
- `uv run black --check app tests`
- `uv run isort --check-only app tests`
- `uv run mypy app`
- `uv run pytest`

Backend tests cover preserved `/api/v1` CRUD, templates, reports, manifest parsing, model connections, MCP runtime behavior, native runtime tools, memory reports, platform runs, and legacy cutover guarantees.

## Frontend Quality Gates

- `pnpm lint`
- `pnpm typecheck`
- `pnpm build`
- `pnpm test:run`
- `pnpm test:e2e`

Frontend tests cover API helpers, query keys, formatting helpers, markdown formatting, portfolio analytics, platform authoring helpers, routed model-connection editor behavior, and browser E2E route families.

## E2E Scope

Playwright runs against backend `8001` and frontend `4173`. Specs cover smoke/navigation, preserved product routes, reports/templates, agent-platform CRUD, output schemas, workflows, runs, agents, and run detail behavior.
