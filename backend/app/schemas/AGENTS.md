# BACKEND SCHEMAS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers Pydantic schema rules.

## OVERVIEW
`app/schemas/` defines request and response contracts with validation, serialization, camelCase aliasing, patch-payload semantics, preserved product payloads, extension state payloads, and current agent-platform payloads. Schemas inherit `CamelModel` for automatic snake_case ↔ camelCase conversion.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

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
| Extension schemas | `extension.py` | bundled extension list/read/toggle payloads with slim public state |
| Agent-platform schemas | `workflow_package.py`, `workflow_package_manifest.py`, `model_connection.py`, `tool.py`, `run.py` | current `/api/*` request and response models |
| Memory domain schemas | `memory.py`, `memory_report.py` | core memory DTO projections plus historical agent-memory report metadata |
| Base/shared schema helpers | `common.py` | `CamelModel`, `TradingSide`, `OperationType`, shared validators |

## CONVENTIONS
- All schemas inherit `CamelModel` from `common.py` for automatic camelCase external representation.
- Read schemas use `model_validate(orm_obj)` to convert ORM entities to Pydantic models.
- Decimal fields serialize to strings via the custom serializer in `CamelModel`.
- Datetime fields serialize to UTC ISO 8601 with a trailing `Z`.
- Enums use string values such as `TradingSide.BUY.value == "BUY"` and `OperationType.DEPOSIT.value == "DEPOSIT"`.
- Extra fields are forbidden to catch typos and unsupported payloads early.
- Update schemas rely on `model_fields_set` to distinguish omitted fields from explicit null or empty updates.
- Portfolio slugs are normalized to lowercase underscore identifiers on create and intentionally omitted from `PortfolioUpdate`.
- `extension.py` keeps bundled extension state aligned with `/api/extensions` and frontend route/tool gating. Public reads expose only `key`, `label`, and `enabled`; toggles accept only `enabled`.
- Agent-platform schemas keep current package artifacts, typed package-local wiring, secret-safe model bindings, run-owned snapshots, and persisted run detail aligned with live `/api/*` contracts and frontend callers.

## ANTI-PATTERNS
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
uv run pytest tests/test_api.py tests/test_workflow_package_runtime_api.py tests/test_memory_domain_schemas.py tests/test_runtime_models.py tests/test_legacy_backend_cutover.py
```

## NOTES
- Market data schemas include `warnings` lists for degraded-state messaging.
- Trading operation schemas use a discriminated union across BUY/SELL/DIVIDEND/SPLIT payloads.
- `workflow_package.py` and `workflow_package_manifest.py` carry current package authoring, validation, import/export, preflight, launch, and artifact payloads.
- `model_connection.py` normalizes OpenAI-family base URLs, rejects empty/null API-key updates, and keeps read payloads secret-safe.
- `extension.py` exposes bundled extension state and enable/disable toggle payloads only.
- `tool.py` exposes read-only server-declared tool metadata.
- `memory.py` defines phase 1 projection boundaries. Model-visible payloads expose `memoryId`, status, summary, provenance, and warnings without report identity, raw markdown, URLs, downloads, or `auditLinks`; API/UI projections may include nested `auditLinks.report`; report routes stay report-shaped.
- `memoryId` is opaque outside `ReportBackedMemoryStore`. Do not parse `mem_<report_id>` in schemas, services, runtime tools, routes, or frontend callers.
- Phase 1 does not have vector search, embeddings, or a memory table, so schema contracts must not imply public memory search or storage routes.
- `run.py` carries global run list/detail, package provenance, rerun, step replay, memory-shaped artifacts, and per-step execution payloads.
- Template schemas expose both inline compile (`POST /templates/compile`) and placeholder-tree browsing (`GET /templates/placeholders`), including report entries in `PlaceholderTreeRead`.
- Report schemas keep `name` and `slug` immutable at the API level by only exposing `content` in `ReportUpdate`; metadata is read-only after creation. `ReportSource` accepts canonical origin values `compiled`, `uploaded`, `external`, and `agent`, while public `ReportCreate` stays true external only. Agent memory metadata keeps purpose/type in `metadata.analysis.reviewType="agent_memory"` and `metadata.analysis.versionGroup="agent_memory/v1"`; server-owned `metadata.createdBy.type="agent"` carries provenance such as `runId`, `agentKey`, and `agentVersion`.
