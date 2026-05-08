# API Design

> Status: Live API reference as of 2026-05-08 (`12ced2d`).

## Conventions

- Health path: `/health`.
- Preserved product base path: `/api/v1`.
- Current agent-platform base path: `/api`.
- Standard format: JSON, except CSV and markdown uploads use `multipart/form-data`.
- External field names are camelCase.
- Decimal money, quantity, and market-value fields serialize as strings.
- Timestamps serialize as UTC ISO 8601 strings.
- Error envelopes use `{code, message, details[]}`.

## Preserved Product API

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

Template/report series can be built by creating a template, previewing with `POST /api/v1/templates/{templateId}/compile`, then saving with `POST /api/v1/reports/compile/{templateId}`. Use the same series value in runtime inputs and report `metadata.tags` so placeholders like `reports.by_tag(inputs.analysis_tag).latest.content` resolve the latest prior report. Report `source` describes origin with canonical values `compiled`, `uploaded`, `external`, and `agent`; public JSON create remains true `external`, while agent-created memory reports use `agent`. For those memory reports, `metadata.analysis.reviewType="agent_memory"` and `metadata.analysis.versionGroup="agent_memory/v1"` describe purpose/type, and server-owned `metadata.createdBy.type="agent"` records provenance such as `runId`, `agentKey`, and `agentVersion`.

## Agent-Platform API

| Resource | Routes |
|---|---|
| Workflow packages | `GET/POST /api/workflow-packages`, `GET/PATCH/DELETE /api/workflow-packages/{packageId}`, `GET /api/workflow-packages/{packageId}/versions`, `POST /api/workflow-packages/validate-manifest`, `POST /api/workflow-packages/import` |
| Package exports and launches | `GET /api/workflow-packages/{packageId}/export`, `POST /api/workflow-packages/{packageId}/preflight`, `GET /api/workflow-packages/{packageId}/launch`, `POST /api/workflow-packages/{packageId}/launches` |
| Model connections | `GET/POST /api/model-connections`, `GET/PATCH/DELETE /api/model-connections/{connectionId}`, connection testing |
| Tools | `GET /api/tools` for read-only server-declared tool metadata |
| Runs | `GET /api/runs`, `GET /api/runs/{runId}`, rerun draft/create, and step replay draft/create routes |

## Platform Compatibility Notes

- Workflow Packages are the only live platform authoring root. Package-private agents, output schemas, capability profiles, private MCP configs, and workflow graphs live inside `ledger.workflowPackage/v1` manifests.
- `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, and `/api/workflows` are removed global authoring routes, not aliases or redirects.
- Package exports omit secrets, encrypted credential payloads, database ids, and run history.
- Model Connections are global live bindings; package manifests store model connection keys, not provider credentials.
- Tools are global read-only metadata from `/api/tools`; runtime tool keys and OpenAI function names stay stable.
- Runs persist package provenance including package id, package key, version, hash, workflow key, and no-secret launch snapshots.

## HTTP Status Guidelines

- `200` for successful reads, updates, previews, compiles, and test responses.
- `201` for create responses, including report create/upload and launch creation.
- `204` for successful delete/archive responses where no body is returned.
- `400` for malformed file or business-rule violations.
- `404` for requested resources that do not exist.
- `409` for uniqueness conflicts such as duplicate slugs/keys/names.
- `422` for request or manifest validation failures.
