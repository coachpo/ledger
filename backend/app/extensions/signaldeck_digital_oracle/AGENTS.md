# DIGITAL ORACLE EXTENSION GUIDE

> Inherits `/AGENTS.md`, `/backend/AGENTS.md`, and `/backend/app/extensions/AGENTS.md`.

## OVERVIEW
`signaldeck_digital_oracle/` owns the bundled `signaldeck.digital_oracle` backend extension. It is tool-only in this upgrade: three server-declared/runtime tools, provider wrappers, normalization mappers, warning models, and extension-owned access-denied messages. It adds no API router, frontend route, nav group, provider bundle, lifecycle hook, or finance behavior.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Extension identity | `ownership.py` | key, label, denied codes/messages, owned tool keys |
| Registrar wiring | `registrars.py`, `tool_specs.py`, `runtime_executors.py` | private contribution loaders for server metadata and runtime tools |
| Provider config/factories | `config.py`, `factory.py`, `provider_inventory.py` | phase-1 provider toggles, item limits, EDGAR contact setting, disabled-provider failures |
| Runtime services | `service.py`, `types.py`, `mappers.py`, `warnings.py` | normalized provider queries/results, runtime result mapping, structured warnings |
| Prediction markets | `runtime_prediction_markets.py` | Polymarket/Kalshi adapters, parser, executor, OpenAI function name |
| SEC filings | `runtime_sec_filings.py` | EDGAR adapter, ticker/CIK lookup, parser, executor, contact-email requirement |
| Market sentiment | `runtime_market_sentiment.py` | Fear & Greed adapter, parser, executor |
| Coverage | `../../../../tests/test_runtime_tools.py`, `../../../../tests/fixtures/digital_oracle/` | tool keys, disabled-extension behavior, mocked phase-1 runtime dispatch |

## CONVENTIONS
- Tool keys use the canonical `signaldeck.<owner>.<tool_collection>.<tool>` contract and are the only public keys for this extension: `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, and `signaldeck.digital_oracle.market_sentiment.lookup`. OpenAI function names are the mechanical underscore mappings `signaldeck_digital_oracle_prediction_markets_lookup`, `signaldeck_digital_oracle_sec_filings_lookup`, and `signaldeck_digital_oracle_market_sentiment_lookup`.
- Provider wrappers may call upstream HTTP APIs, but the extension must keep phase-1 boundaries explicit: do not vendor `digital-oracle` or require `yfinance`.
- Runtime parsers reject unsupported fields and normalize inputs before service calls; executors return Pydantic `model_dump(mode="json", by_alias=True)` payloads.
- Structured warnings are part of successful degraded responses. Do not treat missing, stale, malformed, disabled, or partial provider coverage as fatal unless the parser/config contract says so.
- SEC filings require backend `DIGITAL_ORACLE_EDGAR_CONTACT_EMAIL`; do not ask models or users for that configured contact email during tool execution.
- Keep provider DTOs and model-visible results free of raw upstream payloads.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not add API routers, frontend routes, nav entries, provider bundles, or lifecycle hooks here in this upgrade.
- Do not move Digital Oracle tool implementations into platform-core runtime modules.
- Do not reuse Finance Workspace report/memory ownership for Digital Oracle outputs.
- Do not change tool keys, OpenAI function names, denied messages, or result shapes without updating runtime/tool-catalog/package tests.

## VALIDATION
```bash
cd backend
uv run pytest tests/test_runtime_tools.py tests/test_tool_catalog_api.py tests/test_extension_lifecycle_matrix.py
```
