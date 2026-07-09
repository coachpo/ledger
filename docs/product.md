# SignalDeck Product

SignalDeck is a self-hosted mini-Jenkins for LLM agents. Operators define multi-agent workflows as YAML Workflow Packages, run them manually or on schedules, and inspect queued execution, step evidence, final outputs, and generated reports.

## Scope

SignalDeck is trusted single-user software. Public user authentication, RBAC, organizations, tenant management, plugin marketplaces, live broker execution, portfolio accounting, workflow memory, run forks, Studio, Tryout, orchestration, runtime-v2, simulations, and backtests are not product surfaces unless the project is explicitly re-scoped.

The live browser routes are:

- `/templates` and `/reports` for preserved finance template/report work.
- `/workflow-packages` for YAML package authoring, validation, import, export, and package secret bindings.
- `/workflow-packages/:packageId/run` for launch preflight and manual run creation.
- `/scheduled-tasks` for recurring Workflow Package runs.
- `/model-connections` for encrypted model/provider bindings.
- `/runs` for run list, run detail, and rerun.

The live backend APIs are:

- `/api/v1/templates` and `/api/v1/reports`, contributed by `signaldeck.finance`.
- `/api/workflow-packages`, `/api/schedules`, `/api/model-connections`, `/api/tools`, and `/api/runs`.

## Workflow Packages

Workflow Packages are the only executable authoring root. A package manifest uses `signaldeck.workflowPackage/v1` YAML and owns package-local agents, `systemPrompt` methodology, output schemas, capability profiles, private MCP configs, HTTP operation nodes, workflow graphs, and dependency references.

Package manifests reference Model Connections by stable global key and runtime tools by canonical owner-qualified tool key. Package-private MCP `env`, `headers`, and `query` values are secret-bearing runtime config; browser reads and exports omit those values along with database ids, run history, package secret binding rows, and raw secret values.

The parser rejects YAML aliases, anchors, merge keys, unsupported tags, non-finite numbers, duplicate local refs, raw global ids, legacy `spec.skills`, and legacy `spec.memory`.

## Runs

Launches and scheduled fires create queued runs with immutable package snapshots and resolved non-secret Model Connection runtime profiles. The scheduler worker claims queued runs, dispatches agents and HTTP operations from the snapshot, and stores run evidence.

Run detail exposes canonical inputs, package provenance, queue/progress state, steps, agent invocations, HTTP operation invocations, token usage, optional trace/span ids, typed failure taxonomy, bounded tool-call correction retries, transient provider retry metadata when emitted, and final output. Rerun edits root launch parameters and links back to the source run.

## Scheduled Tasks

Scheduled Tasks target one current Workflow Package workflow. They use structured `interval`, `daily`, `weekly`, or `monthly` recurrence with an IANA timezone, overlap and misfire policies, JSON input templates, preview without persistence, run-now, and schedule-owned fire history while the schedule exists.

Deleting a schedule deletes future automation and schedule-owned fire rows while preserving existing runs through run-owned schedule provenance.

## Model Connections And Tools

Model Connections are global encrypted provider/model bindings. Writes select connection identity, endpoint/model settings, `protocolProfile`, timeout, reasoning effort, and write-only API key values; backend services own capability evidence, policy defaults, probe metadata, reachability-test metadata, and runtime-profile truth.

`/api/tools` is read-only server-declared metadata from statically installed extensions. Packages grant tools through local capability profiles; unsupported native tool names fail closed and do not fall through to MCP fallback.

`signaldeck.finance` contributes market data, OHLCV/history, indicators, fundamentals, news, social sentiment, insider data, and report lookup tools. `signaldeck.digital_oracle` contributes prediction markets, SEC filings, market sentiment, macro/rates, crypto derivatives, CFTC positioning, and options tools. OpenAI function names are the mechanical underscore mapping from canonical keys.

## Templates And Reports

Templates support the `inputs` and `reports` placeholder roots, inline compile, stored-template compile, placeholder browsing, and runtime input metadata. JSON Schema `title` and `description` are display metadata only and do not change runtime payloads.

Reports are point-in-time markdown snapshots keyed by unique slug. Sources are `compiled`, `uploaded`, `external`, and `agent`; `external` is only for true external user/API-created reports.

## Static Extensions

Extensions are private Python wiring, not a marketplace. `INSTALLED_EXTENSIONS` declares bundled extension instances, validates unique extension/tool keys, and contributes API routers, runtime tool declarations/specs, providers, and dependency surfaces.

`signaldeck.finance` owns the preserved template/report route families plus finance runtime tools/providers. `signaldeck.digital_oracle` is tool-only and adds no route or nav surface.

## Operations

`start.sh` is the authoritative local/demo launcher. The root Dockerfile and root Compose stack are local/demo only; production uses the supported backend and frontend images.

Schema changes require a database rebuild. Startup uses SQLAlchemy `create_all`, bundled package seeds, and stale-run recovery instead of Alembic migrations.

Deploy behind `SIGNALDECK_API_TOKEN` or an authenticated reverse proxy, use HTTPS, and keep PostgreSQL private. Production requires non-placeholder `AGENT_PLATFORM_ENCRYPTION_KEY` values and regular PostgreSQL backups.

## Validation

CI is the test plan: version sync, backend quality, frontend quality, frontend E2E, and Docker image publishing. Local full validation is:

```bash
(cd backend && uv run ruff check app tests && uv run black --check app tests && uv run isort --check-only app tests && uv run mypy app && uv run pytest)
(cd frontend && pnpm lint)
(cd frontend && pnpm typecheck)
(cd frontend && pnpm build)
(cd frontend && pnpm test:run)
(cd frontend && pnpm exec playwright install --with-deps chromium && pnpm test:e2e)
```
