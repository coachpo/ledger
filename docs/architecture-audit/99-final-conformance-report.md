# Final Architecture Conformance Report

## Verdict
PASS WITH RISKS.

The package-first architecture cleanup is conformant across backend contracts, frontend route/navigation contracts, persistence/bootstrap, extension boundaries, memory/tools, and documentation. Backend and frontend full quality gates pass. The required default Playwright command is the only non-green practical gate: it fails under this local run's default 12-worker E2E environment with SQLAlchemy connection-pool exhaustion, while the same 35 browser tests pass with `--workers=1`.

## Checked S2-S15 Summary
| Slice | Status | Final classification |
| --- | --- | --- |
| S2 Route/API Surface Cleanup | Closed | Removed route families are absent/404/NotFound; live platform and finance routes remain. |
| S3 Backend Boundaries | Closed | No non-API runtime/service/model/repository module imports API routers; no compatibility re-export was needed. |
| S4 Workflow Package Manifest | Closed | Manifests reject legacy/global/unsafe syntax and keep resources package-local. |
| S5 Export/Launch/Preflight | Closed | Private MCP `env`, `headers`, and `query` are omitted from exports/browser reads; launch queues runs. |
| S6 Worker Runtime Execution | Closed | Active lease owner is rechecked before result persistence and terminal finalization. |
| S7 Scheduled Tasks | Closed | Structured recurrence, preview, run-now, fire materialization, and queued execution are current-contract only. |
| S8 Model Connections/Secrets/HTTP | Closed | Public reads are secret-safe; HTTP operation execution fails closed. |
| S9 Tools/Runtime Dispatch | Closed | `/api/tools` is metadata-only; runtime dispatch enforces grants and extension state. |
| S10 Platform-Core Memory | Closed | Memory writes require explicit private scope and package/runtime context where applicable. |
| S11 Extensions/Finance Isolation | Closed | Extension DTOs are slim, Finance is gated and extension-owned, Digital Oracle is tool-only. |
| S12 Frontend Package-First UX | Closed | Removed routes hit NotFound; editor and launch are split; Digital Oracle UI routes are absent. |
| S13 Persistence/Migration Cleanup | Closed | Retired global authoring tables are absent/drop-only and not startup repair targets. |
| S14 API/Docs Cleanup | Closed | API conventions and live docs align with current contracts and canonical owner docs. |
| S15 Full Verification | Closed with risk | Full backend/frontend gates pass; default E2E is blocked by local parallel pool capacity, sequential E2E passes. |

## Route And API Surface
Backend live surface is `/health`, `/ready`, platform `/api/extensions`, `/api/memory`, `/api/model-connections`, `/api/tools`, `/api/workflow-packages`, `/api/schedules`, and `/api/runs`, plus Finance-owned gated `/api/v1` portfolio, balance, position, trading-operation, market-data, template, and report route families. Removed `/api/agents`, `/api/workflows`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, `/api/skills`, Studio, Tryout, orchestration, and runtime-v2 surfaces remain absent.

Frontend live surface is `/`, `/extensions`, `/workflow-packages`, `/workflow-packages/:packageId/run`, `/scheduled-tasks`, `/model-connections`, `/memory`, `/runs`, and Finance Workspace routes assembled through the Finance extension. The catch-all route owns product 404 behavior. Digital Oracle has no route or nav contribution.

## Deleted Or Obsolete Legacy Behavior
- Standalone global executable authoring is obsolete: agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, runtime-v2, orchestration, simulations, and backtests are not live acceptance paths.
- Retired global authoring persistence is no longer startup-owned; retired tables are drop-only cleanup targets.
- Inline launch execution is absent from API handlers; launch creates queued runs and workers execute claimed snapshots.
- Raw cron schedule authoring is absent from live schedule contracts.
- Private MCP request config is no longer export/browser-visible material.
- Duplicate docs such as `docs/api-design.md`, `docs/signaldeck-agent-platform.md`, and `docs/signaldeck-memory-layer-design.md` were not recreated.

## Package-First Runtime And Worker Summary
Workflow Packages are the only executable authoring root. Package-private agents, output schemas, capability profiles, MCP configs, workflow graphs, HTTP nodes, runtime inputs, and secret refs live in package artifacts or package-owned runtime records. Launch/preflight reads current package state, creates immutable run provenance, and queues durable runs. The scheduler worker materializes due schedule fires, claims queued runs, heartbeats leases, recovers stale leases, executes snapshots, and finalizes only when the active claim still owns the run.

## Extension, Memory, Tool, And Secret Boundaries
Extensions are statically resident and exposed publicly only as `key`, `label`, and `enabled`. Finance owns preserved finance routes, nav, server-declared tools, runtime tools, provider bundles, and report-domain history. Digital Oracle owns only its three tool keys/OpenAI function names and has no UI surface. Platform memory is core-owned, scoped, opaque-id based, report-free for canonical memory, and visible as core tools when bundled extensions are disabled. `/api/tools` remains read-only metadata; runtime dispatch is separate and grant/extension aware. Model/package secrets are encrypted at rest and never returned in public reads, exports, or browser previews.

## Gap Register Classification
- GAP-001: Closed by S2, S4, S12, and S13.
- GAP-002: Closed by S13.
- GAP-003: Closed by S5.
- GAP-004: Closed by S6.
- Deferred gaps: none.
- Obsolete gaps/behaviors: removed legacy/global authoring, retired-table repair ballast, export-preserved MCP private config, and unclaimed terminal writes.

## Commands And Results
| Command | Result | Evidence |
| --- | --- | --- |
| `cd backend && uv run ruff check app tests && uv run black --check app tests && uv run isort --check-only app tests && uv run mypy app && uv run pytest` | PASS, exit 0; `948 passed, 1 warning` | `.omo/evidence/slice-s15/backend-full.txt` |
| `cd frontend && pnpm lint && pnpm typecheck && pnpm build && pnpm test:run` | PASS, exit 0; `565 passed`; existing Vite chunk-size warning | `.omo/evidence/slice-s15/frontend-full.txt` |
| `cd frontend && pnpm test:e2e` | Environment-blocked, exit 1; default 12 workers exhausted SQLAlchemy pool; `25 passed`, `10 failed` downstream | `.omo/evidence/slice-s15/frontend-e2e.txt` |
| `cd frontend && pnpm exec playwright test --workers=1` | PASS, exit 0; `35 passed` | `.omo/evidence/slice-s15/frontend-e2e-workers1.txt` |
| S15 static conformance searches | PASS for hard gates | `.omo/evidence/slice-s15/conformance-static-raw.txt`, `.omo/evidence/slice-s15/conformance.md` |

## Changed File Categories
The cumulative dirty tree covers backend runtime/queue/persistence/service/test cleanup, frontend route/E2E/package-authoring test cleanup, canonical docs/audit docs, and `.omo` evidence/notepad files. `docs/architecture-audit/99-final-conformance-report.md` is the S15-owned source doc. `.omo/evidence/slice-s15/changed-files.txt` records the current unstaged status. No files were staged or committed.

## Residual Risks
- The default E2E command is not green in this local environment when Playwright uses 12 workers against the backend test database/pool. Sequential E2E passing narrows this to test-environment capacity, but CI/default worker configuration may need an explicit worker limit or backend pool adjustment if default parallelism is intended to be supported.
- The frontend production build retains the existing Vite chunk-size warning; this is not new in S15 and does not block conformance.
- Retired global authoring modules may still exist as quarantined non-live remnants, but current app imports and startup repair are guarded by tests and static evidence.

## Guardrails
- Do not reintroduce global executable authoring routes, compatibility redirects, dual DTOs, raw cron, Digital Oracle UI, startup repair for retired global authoring tables, or export of private MCP request config.
- Keep Workflow Packages as the sole executable authoring root and keep package-private resources artifact-local.
- Keep launch queue-only and worker-owned, with active lease ownership required for terminal writes.
- Keep platform-core tools/memory separate from Finance report tooling and extension-owned runtime providers.
- Keep live docs limited to the canonical owner docs plus architecture-audit evidence; do not present pending-design or absent duplicate docs as current source of truth.
