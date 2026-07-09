# SignalDeck Product

SignalDeck is a self-hosted mini-Jenkins for LLM agents. Operators define
multi-agent workflows as YAML Workflow Packages, launch them manually or on
schedules, and inspect queued execution, evidence, final outputs, templates, and
reports from one trusted single-user app.

## Scope

SignalDeck is trusted single-user software. Public user authentication, RBAC,
organizations, tenant management, plugin marketplaces, live broker execution,
portfolio accounting, workflow memory, run forks, Studio, Tryout,
orchestration, runtime-v2, simulations, and backtests are not product surfaces
unless the project is explicitly re-scoped.

The browser app ships these route families:

- `/` dashboard for recent runs, status counts, and active-run polling.
- `/templates`, `/templates/new`, and `/templates/:templateId/edit`.
- `/reports` and `/reports/:slug`.
- `/workflow-packages`, `/workflow-packages/import`, `/workflow-packages/new`,
  `/workflow-packages/:packageId`, and `/workflow-packages/:packageId/run`.
- `/scheduled-tasks`, `/scheduled-tasks/new`, and
  `/scheduled-tasks/:scheduleId`.
- `/model-connections`, `/model-connections/new`, and
  `/model-connections/:modelConnectionId/edit`.
- `/runs` and `/runs/:runId`.

The backend exposes `/health` and `/ready`, finance APIs under `/api/v1`, and
platform APIs under `/api`:

- `/api/v1/templates` and `/api/v1/reports`, contributed by
  `signaldeck.finance`.
- `/api/workflow-packages`, `/api/schedules`, `/api/model-connections`,
  `/api/tools`, and `/api/runs`.

## Workflow Packages

Workflow Packages are the only executable authoring root. A package manifest
uses `signaldeck.workflowPackage/v1` YAML and owns `spec.inputs`, package-local
agents, output schemas, capability profiles, private MCP server configs, HTTP
operation nodes, and workflow graphs.

Workflow graph node kinds are `step`, `http`, `sequence`, `fanout`, and `loop`.
Step and HTTP request references can target `inputs.<path>` or
`nodes.<nodeId>.outputs.<slot>[.<path>]`. Workflow outputs must reference node
outputs. Secret references use `${{ secrets.<key> }}` and are only accepted in
HTTP request fields. HTTP operation preflight currently allows `GET` and `POST`.

Package manifests reference Model Connections by stable global key and runtime
tools by canonical owner-qualified tool key. Package-private MCP `env`,
`headers`, and `query` values are secret-bearing runtime config. Manifest
source/package-definition payloads and export YAML omit secret-bearing inline
MCP values, raw secret values, database ids, run history, and package secret
binding rows; API response envelopes can still include package identity such as
`packageId` and `packageKey`. The separate Secret Bindings API/UI exposes only
key, presence, and timestamps, never the stored value.

The parser rejects YAML aliases, anchors, merge keys, unsupported tags,
non-finite numbers, duplicate YAML keys, duplicate local refs, raw database ids,
secret-like manifest fields, `spec.skills`, closed-object schema keywords such
as `additionalProperties`, and unknown manifest fields.

## Runs

Launches and scheduled fires create queued runs with immutable package snapshots
and resolved non-secret Model Connection runtime profiles. The scheduler worker
claims queued runs, dispatches agents and HTTP operations from the snapshot, and
stores run evidence.

Run detail exposes canonical inputs, package provenance, queue/progress state,
steps, agent invocations, HTTP operation invocations, token usage, optional
trace/span ids, typed failure taxonomy, bounded tool-call correction retries,
transient provider retry metadata when emitted, and final output. Package
provenance returns a safe manifest source and package definition, and redacts
package-private MCP `env`, `headers`, and `query` values from compiled-plan
reads.

`POST /api/runs/{id}/cancel` cancels queued runs immediately; running runs stop
cooperatively at step boundaries. `GET /api/runs/{id}/rerun-draft` and
`POST /api/runs/{id}/reruns` create reruns from the frozen snapshot while
allowing root launch parameter edits. `DELETE /api/runs/{id}` removes one run.

## Scheduled Tasks

Scheduled Tasks target one current Workflow Package workflow. They use
structured `interval`, `daily`, `weekly`, or `monthly` recurrence with an IANA
timezone, overlap and misfire policies, JSON input templates, preview without
persistence, run-now, and schedule-owned fire history while the schedule exists.

Schedule input templates can reference `schedule`, `fire`, `window`, `lastRun`,
and `vars` placeholders. Deleting a schedule deletes future automation and
schedule-owned fire rows while preserving existing runs through run-owned
schedule provenance.

## Model Connections And Tools

Model Connections are global encrypted provider/model bindings. Writes select
connection identity, endpoint/model settings, `protocolProfile`, timeout,
reasoning effort, and write-only API key values. Backend services own capability
evidence, runtime policy defaults, probe metadata, reachability-test metadata,
and runtime-profile truth.

`/api/tools` is read-only server-declared metadata from statically installed
extensions. Packages grant tools through local capability profiles. Unsupported
native tool names fail closed instead of silently falling through to MCP
fallback. OpenAI function names are the mechanical underscore mapping from
canonical tool keys.

`signaldeck.finance` contributes market data, OHLCV/history, indicators,
fundamentals, news, social sentiment, insider data, and report lookup tools.
`signaldeck.digital_oracle` contributes prediction markets, SEC filings, market
sentiment, macro/rates, crypto derivatives, CFTC positioning, and options tools.

## Templates And Reports

Templates support markdown authoring, `{{placeholders}}`, runtime inputs, inline
compile preview, stored-template compile, placeholder browsing, save/delete, and
report generation. JSON Schema `title` and `description` are display metadata
only and do not change runtime payloads.

Reports are point-in-time markdown snapshots keyed by unique slug. They can be
generated from templates, uploaded as UTF-8 markdown, created by API, edited by
content, downloaded, filtered, and deleted. Sources are `compiled`, `uploaded`,
`external`, and `agent`; `external` is only for true external user/API-created
reports.

## Static Extensions

Extensions are private Python wiring, not a marketplace. `INSTALLED_EXTENSIONS`
declares bundled extension instances, validates unique extension/tool keys, and
contributes API routers, runtime tool declarations/specs, providers, dependency
surfaces, and package-private MCP tool ownership.

`signaldeck.finance` owns the preserved template/report route families plus
finance runtime tools/providers. `signaldeck.digital_oracle` is tool-only and
adds no route or nav surface.

## Operations

`start.sh` is the authoritative local/demo launcher. It builds the root
combined local/demo image and exposes only `http://localhost:${APP_PORT:-8080}`.
The root Dockerfile and root Compose stack are local/demo only.

Production uses the supported backend and frontend images. The backend image
serves the API by default and also runs the scheduler role when started with
`python -m app.workers.run_scheduler`; the scheduler role is required because
launches only enqueue runs. The frontend production image serves the browser app
and proxies same-origin `/api` requests to `BACKEND_UPSTREAM`.

Schema changes require a database rebuild. Startup uses SQLAlchemy `create_all`,
bundled package seeds, and stale-run recovery instead of Alembic migrations.
Run retention is disabled unless `SIGNALDECK_RUN_RETENTION_DAYS` is set and
prunes terminal runs by `finished_at`.

Development validation targets Python 3.13 and Node 24 because that is what CI
uses. Production Dockerfiles currently build on Python 3.14 and Node 26. Both
the root local/demo image and frontend production image install
`pnpm@10.30.1` with `npm install -g pnpm@10.30.1`; do not reintroduce
`corepack enable` for Node 26 images.

FastAPI is temporarily capped at `<0.137` until Logfire allows
`opentelemetry-sdk>=1.43` and `opentelemetry-instrumentation-fastapi>=0.64b0`.
The cap protects 405/partial-route-match requests from a runtime crash in older
OpenTelemetry FastAPI instrumentation.

When `SIGNALDECK_API_TOKEN` is set, all non-`OPTIONS` paths except `/health`
and `/ready` require `Authorization: Bearer <token>`. Deploy behind that token
or an authenticated reverse proxy, use HTTPS, and keep PostgreSQL private.
Production requires non-placeholder `AGENT_PLATFORM_ENCRYPTION_KEY` values. Back
that key up with PostgreSQL because losing it makes stored Model Connection and
package-secret values undecryptable.

## Validation

CI is the test plan: version sync, backend quality, frontend quality, frontend
E2E, and Docker image publishing. `docker-images.yml` builds only
`backend/Dockerfile` and `frontend/Dockerfile`; the root local/demo Dockerfile
must be checked with a local `docker build .` when it changes. Local full
validation is:

```bash
(cd backend && uv sync)
(cd frontend && pnpm install)
(cd backend && uv run ruff check app tests && uv run black --check app tests && uv run isort --check-only app tests && uv run mypy app && uv run pytest)
(cd frontend && pnpm lint)
(cd frontend && pnpm typecheck)
(cd frontend && pnpm build)
(cd frontend && pnpm test:run)
(cd frontend && pnpm exec playwright install --with-deps chromium && pnpm test:e2e)
git diff --check
```
