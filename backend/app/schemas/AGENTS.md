# BACKEND SCHEMAS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers Pydantic schema rules.

## OVERVIEW
`app/schemas/` defines request and response contracts with validation, serialization, camelCase aliasing, patch-payload semantics, preserved product payloads, extension state payloads, and current agent-platform payloads. Schemas inherit `CamelModel` for automatic snake_case ↔ camelCase conversion.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio schemas | `portfolio.py` | slug validation, immutable-on-update contract, summary counts |
| Balance schemas | `balance.py` | `BalanceCreate`, `BalanceRead`, `BalanceUpdate` |
| Position schemas | `position.py` | CRUD plus symbol lookup response |
| Trading operation schemas | `trading_operation.py` | discriminated create union plus read/result models |
| Market data schemas | `market_data.py` | quote/history payloads plus warning fields |
| CSV import schemas | `csv_import.py` | preview and commit payloads |
| Template schemas | `text_template.py` | CRUD, inline compile, stored compile, placeholder tree |
| Report schemas | `report.py` | read/update payloads plus metadata envelope |
| Extension schemas | `extension.py` | statically resident extension list/read/toggle payloads with slim public state |
| Agent-platform schemas | `workflow_package.py`, `workflow_package_manifest.py`, `schedule.py`, `model_connection.py`, `tool.py`, `run.py` | current `/api/*` request and response models |
| Workflow memory schemas | `workflow_memory.py` | proposal review, audit event, quarantine, approval, and rejection payloads for `/api/memory` review APIs |
| Base/shared schema helpers | `common.py` | `CamelModel`, `TradingSide`, `OperationType`, shared validators |

## CONVENTIONS
- All schemas inherit `CamelModel` from `common.py` for automatic camelCase external representation.
- Read schemas use `model_validate(orm_obj)` to convert ORM entities to Pydantic models.
- Decimal fields serialize to strings via the custom serializer in `CamelModel`.
- Datetime fields serialize to UTC ISO 8601 with a trailing `Z`.
- Enums use string values such as `TradingSide.BUY.value == "BUY"` and `OperationType.DEPOSIT.value == "DEPOSIT"`.
- Extra fields are forbidden to catch typos and unsupported payloads early.
- Update schemas rely on `model_fields_set` to distinguish omitted fields from explicit null or empty updates.
- Portfolio slugs are normalized to lowercase underscore identifiers on create and intentionally omitted from `PortfolioUpdate`; portfolio schemas do not expose `baseCurrency`/`base_currency`.
- `extension.py` keeps statically resident extension state aligned with `/api/extensions` and frontend route/tool gating. Public reads expose only `key`, `label`, and `enabled`; toggles accept only `enabled`.
- Agent-platform schemas keep current package artifacts, typed package-local wiring, schedule recurrence/fire payloads, secret-safe model bindings, run-owned snapshots, and persisted run detail aligned with live `/api/*` contracts and frontend callers.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not hand-build camelCase dicts; use `model_validate()` or `.model_dump()`.
- Do not skip validation on create or update schemas.
- Do not use `float` for money or quantity; keep `Decimal`, `int`, or `str` depending on the contract.
- Do not bypass `CamelModel` aliasing; external JSON must stay camelCase.
- Do not change template placeholder or compile payload shapes without updating the frontend types and editor.
- Do not change preserved-product, extension, or agent-platform payload shapes without updating the corresponding backend routes, frontend types, and regression tests together.
- Do not add plugin-manifest metadata to extension reads or run dependency records. Registry and scaffold data stay outside public schemas.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_workflow_package_runtime_api.py tests/test_workflow_memory_policy.py tests/test_runtime_models.py tests/test_legacy_backend_cutover.py
```

## NOTES
- Market data schemas include `warnings` lists for degraded-state messaging.
- Trading operation schemas use a discriminated union across BUY/SELL/DIVIDEND/SPLIT payloads.
- `workflow_package.py` and `workflow_package_manifest.py` carry current package authoring, validation, import/export, preflight, launch, and artifact payloads.
- `schedule.py` carries Scheduled Task list/detail/create/update/delete, structured recurrence, preview, fire history, and run-now contracts; raw cron is not a live schema shape.
- `model_connection.py` normalizes OpenAI-family base URLs, rejects empty/null API-key updates, and keeps read payloads secret-safe.
- `extension.py` exposes statically resident extension state and enable/disable toggle payloads only.
- `tool.py` exposes read-only server-declared tool metadata.
- `workflow_memory.py` defines review-only workflow memory API boundaries: proposal listing, approve/reject actions, audit events, and quarantine evidence. It does not expose browser memory CRUD, global search, or direct model tool payloads.
- Workflow memory identifiers are opaque platform-core identifiers. Do not parse them in schemas, services, routes, runtime tools, or frontend callers.
- Workflow Package `spec.memory` and service-layer policy determine context injection and proposal activation; schema contracts must not imply browser memory search/storage surfaces.
- `run.py` carries global run list/detail, backend-owned `progress` and nullable `queue` read models, package provenance, rerun, invocation-input fork, historical replay lineage reads, `workflowMemoryEvidence`, and per-step execution payloads.
- Template schemas expose both inline compile (`POST /templates/compile`) and placeholder-tree browsing (`GET /templates/placeholders`), including report entries in `PlaceholderTreeRead`.
- Report schemas keep `name` and `slug` immutable at the API level by only exposing `content` in `ReportUpdate`; metadata is read-only after creation. `ReportSource` accepts canonical origin values `compiled`, `uploaded`, `external`, and `agent`, while public `ReportCreate` stays true external only. Agent memory metadata keeps purpose/type in `metadata.analysis.reviewType="agent_memory"` and `metadata.analysis.versionGroup="agent_memory/v1"`; server-owned `metadata.createdBy.type="agent"` carries provenance such as `runId`, `agentKey`, and `agentVersion`.
