# BACKEND SCHEMAS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers Pydantic schema rules.

## OVERVIEW
`app/schemas/` defines request and response contracts with validation, serialization, camelCase aliasing, patch-payload semantics, the preserved product payloads, and the current agent-platform payloads. Schemas inherit `CamelModel` for automatic snake_case ↔ camelCase conversion.

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
| Agent-platform schemas | `agent.py`, `skill.py`, `mcp_server.py`, `output_schema.py`, `workflow.py`, `run.py` | current `/api/*` request and response models |
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
- Agent-platform schemas keep immutable versions, typed workflow wiring, and persisted run detail aligned with the live `/api/*` contracts and frontend callers.

## ANTI-PATTERNS
- Do not hand-build camelCase dicts; use `model_validate()` or `.model_dump()`.
- Do not skip validation on create or update schemas.
- Do not use `float` for money or quantity; keep `Decimal`, `int`, or `str` depending on the contract.
- Do not bypass `CamelModel` aliasing; external JSON must stay camelCase.
- Do not change template placeholder or compile payload shapes without updating the frontend types and editor.
- Do not change preserved-product or agent-platform payload shapes without updating the corresponding backend routes, frontend types, and regression tests together.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_runtime_api.py tests/test_runtime_models.py tests/test_legacy_backend_cutover.py
```

## NOTES
- Market data schemas include `warnings` lists for degraded-state messaging.
- Trading operation schemas use a discriminated union across BUY/SELL/DIVIDEND/SPLIT payloads.
- `output_schema.py` carries the saved-schema, builder, preview, and validation-detail payloads for the current schema subset.
- `workflow.py` and `run.py` carry the live workflow authoring, run trigger, run list/detail, and per-step execution payloads.
- Template schemas expose both inline compile (`POST /templates/compile`) and placeholder-tree browsing (`GET /templates/placeholders`), including report entries in `PlaceholderTreeRead`.
- Report schemas keep `name` and `slug` immutable at the API level by only exposing `content` in `ReportUpdate`; metadata is read-only after creation.
