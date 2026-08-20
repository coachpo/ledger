# Digital Oracle Extension Guide

## Overview

`signaldeck.digital_oracle` is a static tool-only extension for prediction markets, SEC filings, sentiment, macro/rates, crypto derivatives, CFTC, and options data.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| Extension export | `__init__.py` | Tool declarations and runtime specs only. |
| Tool ownership | `ownership.py` | Canonical tool keys and function names. |
| Runtime dispatch | `runtime_executors.py` | Runtime executor map. |
| Core service | `service.py` | Provider orchestration and result assembly. |
| Providers | `runtime_*_providers.py` | External provider adapters for supported data families. |
| Payload/parsing | `runtime_*_payloads.py`, `runtime_*_parser.py`, `runtime_options_parser.py` | Family-specific normalization and parsing. |
| Runtime modules | `runtime_*.py` | Tool-specific clients, execution wrappers, and result assembly. |

## Conventions

- This extension adds no API router, browser route, nav item, or provider factory.
- Provider failures should produce structured warning results when partial data is useful.
- Optional dependencies stay optional; do not require vendored `digital-oracle` or mandatory `yfinance` for phase 1 behavior.
- FRED and EDGAR secrets are resolved from runtime context/settings where needed and must stay out of reads/logs/catalog metadata.
- Keep parser and payload modules family-specific; avoid one large cross-family normalization switch.
- Runtime result shapes should preserve warnings and source metadata needed for run evidence.

## Anti-Patterns

- Do not make one failed upstream provider fatal when the tool can return bounded partial data.
- Do not add product pages or `/api/v1` routes for this tool-only extension.
- Do not leak provider request headers, keys, or raw stack traces into warnings.
