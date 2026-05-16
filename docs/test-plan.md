# Test Plan

> Status: Live automated-coverage reference for branch `main` at `69e809e`.

## Backend Quality Gates

- `uv run ruff check app tests`
- `uv run black --check app tests`
- `uv run isort --check-only app tests`
- `uv run mypy app`
- `uv run pytest`

Backend tests cover preserved `/api/v1` CRUD, templates, reports, workflow package manifests, package import/export with inline private MCP `env`, `headers`, and `query` values, model connections, slim bundled extension state, extension-filtered global tools, package runtime behavior, dependency-only run extension records, native runtime tools, memory reports, trace metadata, global runs, DB upgrades, and removed-route guarantees.

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

Route-family coverage includes smoke/navigation, portfolio CRUD, reports/templates, the `/extensions` state page, Workflow Packages, Model Connections, Runs, run detail fixtures, package import/export/preflight/launch flows, extension enable/disable gating, and the TradingAgents smoke package as ordinary demo data. Removed-route assertions cover `/skills*`, `/templates/seed`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, `/workflows*`, and legacy navigation entries.

## Extension Metadata Absence Guard

The final cleanup guard searches live code, docs, AGENTS files, and the bundled-extension migration plan for removed public extension metadata names. Allowed matches are destructive upgrade code in `backend/app/db/upgrades.py`, explicit negative-validation tests, legacy-upgrade tests that prove old data is removed or normalized, and private initial-enabled seed wiring in the backend registry/service. Live docs and AGENTS files are not exceptions.

```bash
rg -n "disabled""Reason|disabled_""reason|state""Version|state_""version|contribution""Categories|contribution_""categories|versioning""Rule|versioning_""rule|default""Enabled|default_""enabled|Extension""ContributionRead|extension""Snapshots|extension_""snapshots|Run""ExtensionSnapshotRead" backend frontend docs AGENTS.md .sisyphus/plans/ledger-bundled-extension-migration.md -g '!frontend/retired/**' -g '!frontend/dist/**' -g '!backend/.venv/**' -g '!backend/.mypy_cache/**' -g '!backend/.pytest_cache/**'
```
