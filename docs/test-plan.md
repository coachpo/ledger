# Test Plan

> Status: Live automated-coverage reference for branch `main` at `f9ae90d`.

## Backend Quality Gates

- `uv run ruff check app tests`
- `uv run black --check app tests`
- `uv run isort --check-only app tests`
- `uv run mypy app`
- `uv run pytest`

Backend tests cover preserved `/api/v1` CRUD, templates, reports, artifact-only workflow package dependency persistence, launch/preflight readiness, capability-aware model-connection probes, protocol-profile and policy validation, rerun/fork draft readiness, package import/export with inline private MCP `env`, `headers`, and `query` values, model connections, slim bundled extension state, extension-filtered global tools, package runtime behavior, Model Gateway adapter execution, structured-output strategy selection, native tool-call capability enforcement, provider error normalization, frozen run-owned runtime-profile provenance, backend-owned run progress and queue read models, explicit scheduler worker semantics, dependency-only run extension records, ref-based public invocation payloads, native runtime tools, core memory schemas/services/tools, package-qualified memory scopes, shared-memory mutation conflicts, persisted run memory evidence, historical agent-memory report behavior, trace metadata, global runs, DB upgrades, and removed-route guarantees.

## Frontend Quality Gates

- `pnpm lint`
- `pnpm typecheck`
- `pnpm build`
- `pnpm test:run`
- `pnpm test:e2e`

Frontend tests cover API helpers, query keys, formatting helpers, markdown formatting, portfolio analytics, workflow package helpers, authoring-only package editor flows, Model Connections protocol-profile editing, capability summary rendering, separate reachability-test and capability-probe actions, dedicated `/workflow-packages/:packageId/run` launch page behavior, capability blocker and warning rendering, backend progress/queue consumption in run pages, rerun/fork current-readiness gating, run-detail effective runtime-profile rendering, run-detail memory evidence rendering, layout routing, and browser E2E route families.

## E2E Scope

Playwright uses Chromium only. `frontend/playwright.config.ts` starts a dedicated backend on `8001` and built frontend preview on `4173`.

The backend helper starts the explicit run scheduler worker alongside the Uvicorn backend on `8001` for the Playwright run. It defaults `QUOTE_PROVIDER_BACKEND=deterministic`. The frontend helper builds first, previews with `--strictPort`, and defaults `VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1`.

Specs use API-assisted setup when it keeps UI assertions focused. Preserved product setup uses `/api/v1`; platform setup uses `/api`.

Route-family coverage includes smoke/navigation, portfolio CRUD, reports/templates, the `/extensions` state page, Workflow Packages, Model Connections, Runs, run detail fixtures, package import/export flows, authoring-only package editor behavior, the dedicated `/workflow-packages/:packageId/run` page labeled `Launch Workflow Package`, extension enable/disable gating, and the TradingAgents smoke package as ordinary demo data. Compatibility E2E coverage uses deterministic or fake OpenAI-compatible providers for strict schema, JSON-object fallback, missing native tool-call support, unsupported reasoning fields, and missing usage metadata without live external network dependencies. Frontend removed-route assertions cover `/templates/seed`, `/tryout*`, `/studio*`, `/orchestration*`, `/backtests*`, hidden removed navigation entries, and the absence of live global-authoring routes from the router. Backend removed-surface coverage separately guards `/api/skills` and the removed global-authoring API families.

## Extension Metadata Absence Guard

The final cleanup guard searches live code, docs, and AGENTS files for removed public extension metadata names. Allowed matches are destructive upgrade code in `backend/app/db/upgrades.py`, explicit negative-validation tests, upgrade-normalization tests that prove old data is removed or normalized, and private initial-enabled seed wiring in the backend registry/service. Live docs and AGENTS files are not exceptions.

```bash
rg -n "disabled""Reason|disabled_""reason|state""Version|state_""version|contribution""Categories|contribution_""categories|versioning""Rule|versioning_""rule|default""Enabled|default_""enabled|Extension""ContributionRead|extension""Snapshots|extension_""snapshots|Run""ExtensionSnapshotRead" backend frontend docs AGENTS.md -g '!frontend/retired/**' -g '!frontend/dist/**' -g '!backend/.venv/**' -g '!backend/.mypy_cache/**' -g '!backend/.pytest_cache/**'
```
