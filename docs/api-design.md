# API Design

> Status: Live API reference for branch `main` at `69e809e`.

## Conventions

- Health path: `/health`.
- Preserved product base path: `/api/v1`, contributed by the bundled `signaldeck.finance` extension.
- Current agent-platform base path: `/api`.
- Standard format: JSON, except CSV and markdown uploads use `multipart/form-data`.
- External field names are camelCase.
- Decimal money, quantity, and market-value fields serialize as strings.
- Timestamps serialize as UTC ISO 8601 strings.
- Error envelopes use `{code, message, details[]}`.

## Preserved Product API

The preserved finance product API is bundled as `signaldeck.finance`. It is enabled by default during startup and reset/seed initialization, so local development, tests, and demo packages keep today's behavior without manifest edits. Extension state supports enable and disable only. The generic platform routes, manifest contract, run lifecycle, model bindings, and `/api/tools` host stay core.

| Resource | Routes |
|---|---|
| Portfolios | `GET/POST /api/v1/portfolios`, `GET/PATCH/DELETE /api/v1/portfolios/{portfolioId}` |
| Balances | `GET/POST /api/v1/portfolios/{portfolioId}/balances`, `PATCH/DELETE /api/v1/portfolios/{portfolioId}/balances/{balanceId}` |
| Positions | `GET/POST /api/v1/portfolios/{portfolioId}/positions`, `GET /api/v1/portfolios/{portfolioId}/positions/lookup`, `PATCH/DELETE /api/v1/portfolios/{portfolioId}/positions/{positionId}` |
| CSV import | `POST /api/v1/portfolios/{portfolioId}/positions/imports/preview`, `POST /api/v1/portfolios/{portfolioId}/positions/imports/commit` |
| Trading operations | `GET/POST /api/v1/portfolios/{portfolioId}/trading-operations` |
| Market data | `GET /api/v1/portfolios/{portfolioId}/market-data/quotes`, `GET /api/v1/portfolios/{portfolioId}/market-data/history` |
| Templates | `GET/POST /api/v1/templates`, `GET/PATCH/DELETE /api/v1/templates/{templateId}`, `POST /api/v1/templates/compile`, `GET/POST /api/v1/templates/{templateId}/compile`, `GET /api/v1/templates/placeholders` |
| Reports | `GET/POST /api/v1/reports`, `POST /api/v1/reports/compile/{templateId}`, `POST /api/v1/reports/upload`, `GET/PATCH/DELETE /api/v1/reports/{slug}`, `GET /api/v1/reports/{slug}/download` |

Template/report series can be built by creating a template, previewing with `POST /api/v1/templates/{templateId}/compile`, then saving with `POST /api/v1/reports/compile/{templateId}`. Use the same series value in runtime inputs and report `metadata.tags` so placeholders like `reports.by_tag(inputs.analysis_tag).latest.content` resolve the latest prior report. Report `source` describes origin with canonical values `compiled`, `uploaded`, `external`, and `agent`; public JSON create remains true `external`. Existing `source="agent"` reports with `metadata.analysis.reviewType="agent_memory"` are historical report-domain records only and are not the canonical memory write or lookup substrate.

## Agent-Platform API

| Resource | Routes |
|---|---|
| Workflow packages | `GET/POST /api/workflow-packages`, `GET/PATCH/DELETE /api/workflow-packages/{packageId}`, `GET /api/workflow-packages/{packageId}/manifest`, `POST /api/workflow-packages/validate-manifest`, `POST /api/workflow-packages/import`. Live package reads and writes do not include `status`; stale `status` filters or update fields return `422`. |
| Package secret bindings | `GET /api/workflow-packages/{packageId}/secret-bindings`, `PUT/DELETE /api/workflow-packages/{packageId}/secret-bindings/{key}` |
| Package exports and launches | `GET /api/workflow-packages/{packageId}/export`, `POST /api/workflow-packages/{packageId}/preflight`, `GET /api/workflow-packages/{packageId}/launch`, `POST /api/workflow-packages/{packageId}/launches` |
| Model connections | `GET/POST /api/model-connections`, `GET/PATCH/DELETE /api/model-connections/{connectionId}`, `POST /api/model-connections/{connectionId}/connection-test` |
| Extensions | `GET /api/extensions`, `PATCH /api/extensions/{extensionKey}` for slim bundled extension state. List responses expose only `key`, `label`, and `enabled`; toggle requests accept only `enabled`. |
| Tools | `GET /api/tools` for read-only server-declared market-data, position, report, memory-write, news, insider-data, and `signaldeck.social_sentiment.lookup` tool metadata contributed by currently enabled extensions |
| Runs | `GET /api/runs`, `GET/DELETE /api/runs/{runId}`, `GET /api/runs/{runId}/rerun-draft`, `POST /api/runs/{runId}/reruns`, `GET /api/runs/{runId}/step-replay-draft?stepIndex=...`, `POST /api/runs/{runId}/step-replays` |

## Workflow Package HTTP Nodes and Secret Bindings

Workflow package manifests use `signaldeck.workflowPackage/v1`. The shipped non-agent operation node contract is `kind: http`; `kind: step` continues to mean a local package agent. An HTTP node includes `id`, `slot`, `method`, `url`, optional `headers`, optional `query`, optional JSON-compatible `body`, `response.outputSchema`, `timeoutSeconds`, and `optional`.

`method` is normalized to uppercase and preflight accepts only `GET` and `POST`. `timeoutSeconds` defaults to `30` and is capped at `30` by the manifest schema and runtime settings. The request fields may contain literal JSON values, `${{ inputs.path }}` references, `${{ nodes.node_id.outputs.slot.path }}` references, or `${{ secrets.key }}` references. Secret references are valid only inside HTTP request fields (`url`, `headers`, `query`, and `body`); they are rejected in package metadata, agent fields, schemas, workflow outputs, and other manifest locations.

Package secret bindings are package-local API resources, not manifest/export data. Binding keys must start with a lowercase letter and use only lowercase letters, numbers, and underscores. `GET /api/workflow-packages/{packageId}/secret-bindings` returns `{items:[{packageId,key,hasValue,createdAt,updatedAt}]}`. `PUT /api/workflow-packages/{packageId}/secret-bindings/{key}` accepts `{value}` and stores the value encrypted through the package service; reads only return `hasValue`. `DELETE` removes the binding. Exports omit secret binding rows and raw secret values.

Preflight checks HTTP operations against compiled package data and configured package secret bindings. Missing bindings emit blocking diagnostics such as `HTTP secret binding 'body_token' is not configured` at the operation request path. Unsupported methods, malformed step refs, duplicate operation ids, duplicate step slots, and missing response schemas are blocking errors. Diagnostics and compiled plans must never include raw secret values.

## HTTP Operation Runtime Contract

`HttpOperationExecutionService` is the only execution boundary for `kind: http`. It resolves request values from run inputs, previous step outputs, and package secret bindings immediately before dispatch, then stores redacted request metadata and bounded response metadata on a dedicated operation invocation row.

Production defaults are strict: `HTTP_OPERATION_ALLOWED_METHODS=GET,POST`, `HTTP_OPERATION_ALLOW_INSECURE_HTTP=false`, `HTTP_OPERATION_BLOCK_PRIVATE_NETWORKS=true`, `HTTP_OPERATION_TIMEOUT_MAX_SECONDS=30`, `HTTP_OPERATION_REQUEST_MAX_BYTES=131072`, `HTTP_OPERATION_RESPONSE_MAX_BYTES=262144`, and `HTTP_OPERATION_MAX_REDIRECTS=0`. Dev/test overrides are exercised only by targeted tests; default local HTTP and private/loopback targets remain blocked.

Runtime request metadata redacts sensitive URL query names and all secret-backed headers, query fields, and body fields. Secret-backed metadata is represented as `{from:"secret", key:"...", redacted:true}`. The response contract supports JSON and `text/*` content types, captures status code, selected response headers, content type, body preview, body byte count, body SHA-256, redaction-safe URL, and redirect metadata, then validates the parsed body against `response.outputSchema`. Required operation failures fail the run; optional operation failures persist a failed operation result and return `null` for that slot without failing the whole run.

## Run Detail Shape for Operation Invocations

Run detail payloads expose operations separately from agents. Each `steps[]` item has `invocations` for agent invocations and `operationInvocations` for non-agent operations. Operation invocation records use the operation invocation shape: `id`, `runStepId`, `runId`, `stepIndex`, `slot`, `position`, `operationKey`, `operationKind`, `outputSchemaId`, `outputSchemaVersion`, `method`, `timeoutSeconds`, `requestMetadata`, `responseMetadata`, `graphMetadata`, `optional`, `status`, `output`, `outputOrigin`, `errorCode`, `errorMessage`, `errorDetails`, `durationMs`, `traceSpanId`, replay source fields (`sourceOperationInvocationId`, `sourceRunId`, `sourceRunStepId`, `sourceStepIndex`), timestamps, and update timestamps.

Run list and detail payloads include `extensionDependencies`, a dependency-only array used to explain which extension-owned surfaces the run needed at launch. Each record contains only `extensionKey`, `surfaces`, and `fields`. It is not a plugin manifest, state snapshot, audit log, or public extension metadata carrier.

Operation invocation rows persist in `run_operation_invocations`, not `run_agent_invocations`. Agent-only steps keep `operationInvocations: []`; HTTP-only steps keep `invocations: []`; mixed execution steps may contain both arrays. Reruns and step replays copy operation rows with source-operation provenance while keeping redacted request metadata and response metadata secret-safe.

## Runtime Tool Contract Notes

`/api/tools` is the core global read-only discovery host. Its current finance/product/provider entries come from the bundled `signaldeck.finance` extension, which is enabled by default. Native runtime tools currently include quote/history/OHLCV, indicators, fundamentals, `signaldeck.news.lookup`, `signaldeck.social_sentiment.lookup`, insider data, positions, `signaldeck.reports.lookup`, `signaldeck.memory.write`, and `signaldeck.memory.lookup`. The memory tools are platform-core and remain discoverable when finance is disabled. `signaldeck.social_sentiment.lookup` is a separate tool, not an extension of news lookup; it accepts one symbol plus optional `sources` (`reddit`, `stocktwits`), optional date bounds, and `itemLimit` up to `50`, then returns `sourceBlocks`, aggregate `metrics`, and structured `warnings`.

## Platform Compatibility Notes

- Workflow Packages are the only live platform authoring root. Package-private agents, output schemas, capability profiles, private MCP configs, workflow graphs, and HTTP operation nodes live inside `signaldeck.workflowPackage/v1` manifests.
- `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, and `/api/workflows` are removed global authoring routes, not aliases or redirects.
- Package exports keep private MCP `env`, `headers`, and `query` values inline, omit database ids, run history, live package status, package secret binding rows, and values.
- Model Connections are global live bindings; package manifests store model connection keys, not provider credentials.
- Tools are global read-only metadata from `/api/tools`; finance native tool entries are bundled in `signaldeck.finance`, while runtime tool keys and OpenAI function names stay stable when the extension is enabled.
- `signaldeck.finance` is created enabled by default at startup/reset and supports enable/disable state only. Do not add phase, contribution inventory, versioning, disabled-reason, or state-version fields to public extension responses.
- Runs persist snapshot-based package provenance including copied package id, package key, hashes, workflow key, nullable historical `workflowPackageStatus`, dependency-only `extensionDependencies`, launch parameters, optional Logfire trace ids, per-agent span ids, and per-operation span ids. Current package lookups in provenance do not include live package status.

## HTTP Status Guidelines

- `200` for successful reads, updates, previews, compiles, preflight, manifest validation, connection-test responses, and secret binding updates.
- `201` for create responses, including report create/upload and workflow-package launch creation.
- `204` for successful delete/archive responses where no body is returned.
- `400` for malformed file or business-rule violations.
- `404` for requested resources that do not exist.
- `409` for uniqueness conflicts such as duplicate slugs/keys/names.
- `422` for request, manifest, package, or launch validation failures.
