# Finance Extension Guide

## Overview

`signaldeck.finance` preserves Templates and Reports APIs while contributing finance providers, runtime tools, dependency surfaces, and package-private MCP ownership.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| Extension export | `__init__.py` | Routers, tool declarations, runtime specs, providers. |
| Tool ownership | `ownership.py` | Canonical keys and function names. |
| Provider setup | `provider_factories.py` | Settings-driven provider bundle construction. |
| Runtime dispatch | `runtime_executors.py` | Runtime tool executor map. |
| Market data runtime | `runtime_market_data.py` | Quote/history/indicator/fundamental tools. |
| Report runtime | `runtime_reports.py` | Report lookup tools. |
| Grants | `grant_policy.py` | Explicit runtime grants. |
| Domain services | `services/` | Templates, reports, market data, sentiment/news. |

## Conventions

- Keep `/api/v1/templates` and `/api/v1/reports` stable; these are preserved product surfaces.
- Money, quantities, prices, and market values cross APIs as strings.
- Runtime tools must call `RuntimeToolGrantService` checks for report, quote, and history access.
- Provider construction is settings-driven: Yahoo default, deterministic fallback, ordered news providers, Reddit/StockTwits sentiment adapters, runtime-only Alpha Vantage secrets.
- `web_search_exa` is package-private MCP owned by this extension.
- Runtime-only provider secrets are resolved from runtime context/settings and never returned in dependency surfaces or catalog reads.
- `external` report source is only for true external user/API-created reports.

## Anti-Patterns

- Do not treat finance runtime tools as broker execution or portfolio accounting.
- Do not return raw provider payloads when normalized API/result schemas exist.
- Do not expose stored template/report internals through runtime tool errors.
