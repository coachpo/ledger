# BACKEND SCHEMAS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers Pydantic schema rules.

## OVERVIEW
`app/schemas/` defines request and response contracts with validation, serialization, camelCase aliasing, patch-payload semantics, orchestration payloads, and dedicated runtime, Studio, and Tryout contracts. Schemas inherit `CamelModel` for automatic snake_case ↔ camelCase conversion.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio schemas | `portfolio.py` | slug validation, immutable-on-update contract, summary counts |
| Balance schemas | `balance.py` | `BalanceCreate`, `BalanceRead`, `BalanceUpdate` |
| Position schemas | `position.py` | CRUD plus symbol lookup response |
| Trading operation schemas | `trading_operation.py` | discriminated create union plus read/result models |
| Orchestration schemas | `orchestration.py` | role/character CRUD, mention catalog, versioned updates |
| Runtime schemas | `runtime.py` | runtime runs, artifacts, approvals, trace events, caller filters |
| Studio schemas | `studio.py` | workflow/agent/persona/capability reads plus draft lifecycle payloads |
| Tryout schemas | `tryout.py` | execute, read, and persist contracts keyed by runtime run id |
| Market data schemas | `market_data.py` | quote/history payloads plus warning fields |
| CSV import schemas | `csv_import.py` | preview and commit payloads |
| Template schemas | `text_template.py` | CRUD, inline compile, stored compile, placeholder tree |
| Report schemas | `report.py` | read/update payloads plus metadata envelope |
| Base/shared schema helpers | `common.py` | `CamelModel`, `TradingSide`, `OperationType`, shared validators |

## CONVENTIONS
- All schemas inherit `CamelModel` from `common.py` for automatic camelCase external representation.
- Read schemas use `model_validate(orm_obj)` to convert ORM entities to Pydantic models.
- Decimal fields serialize to strings via the custom serializer in `CamelModel`.
- Datetime fields serialize to UTC ISO 8601 with a trailing `Z`.
- Enums use string values such as `TradingSide.BUY.value == "BUY"` and `OperationType.DEPOSIT.value == "DEPOSIT"`.
- Extra fields are forbidden to catch typos and unsupported payloads early.
- Update schemas rely on `model_fields_set` to distinguish omitted fields from explicit null/empty updates.
- Portfolio slugs are normalized to lowercase underscore identifiers on create and intentionally omitted from `PortfolioUpdate`.
- Orchestration create schemas normalize keys/handles to stable lowercase identifiers, trim optional text fields, and keep update payloads partial while enforcing immutable handles.
- Runtime, Studio, and Tryout schemas are the active execution contract; keep those shapes aligned with the v2 API routes and frontend callers.

## ANTI-PATTERNS
- Do not hand-build camelCase dicts; use `model_validate()` or `.model_dump()`.
- Do not skip validation on create or update schemas.
- Do not use `float` for money or quantity; keep `Decimal`, `int`, or `str` depending on the contract.
- Do not bypass `CamelModel` aliasing; external JSON must stay camelCase.
- Do not change template placeholder or compile payload shapes without updating the frontend types and editor.
- Do not change orchestration role/character/mention-catalog payload shapes without updating `app/api/orchestration.py`, `app/services/orchestration_service.py`, frontend orchestration callers, and regression tests together.
- Do not change workflow-spec, runtime, Studio, or Tryout payload shapes without updating the corresponding v2 API routes, frontend types, and regression tests together.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_runtime_schemas.py tests/test_orchestration_api.py
```

## NOTES
- Market data schemas include `warnings` lists for degraded-state messaging.
- Trading operation schemas use a discriminated union across BUY/SELL/DIVIDEND/SPLIT payloads.
- `orchestration.py` exposes versioned role/character read models, keeps `roleKey` on character reads, and returns the mention catalog as a first-class response shape.
- `runtime.py` defines the active run, artifact, approval, and trace payloads used by both public runtime routes and Studio inspection views.
- `studio.py` carries the managed catalog and lifecycle payloads for workflow specs, agent specs, personas, and capabilities.
- `tryout.py` keeps execute/read/persist contracts tied to runtime-backed runs.
- Template schemas expose both inline compile (`POST /templates/compile`) and placeholder-tree browsing (`GET /templates/placeholders`), including report entries in `PlaceholderTreeRead`.
- Report schemas keep `name` and `slug` immutable at the API level by only exposing `content` in `ReportUpdate`; metadata is read-only after creation.
