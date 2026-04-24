# BACKEND CORE GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers `app/core/`.

## OVERVIEW
`app/core/` owns cached settings, error-envelope helpers, normalization/decimal/time utilities, and small constants shared across API, services, schemas, and DB code.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Settings / env aliases | `config.py` | `Settings`, env aliases, cached `get_settings()` |
| Error envelope / helpers | `errors.py` | `ApiError`, `not_found_error`, `business_rule_error`, validation details |
| Decimal / symbol / timezone helpers | `formatting.py` | decimal parsing/stringification, symbol/currency normalization, UTC helpers, `utcnow()` |
| Shared constants | `constants.py` | CSV import mode, money zero, small shared constants |

## CONVENTIONS
- `get_settings()` is cached; tests reset it with `reset_settings_cache()` when env values change.
- Runtime config uses env aliases such as `DATABASE_URL`, `QUOTE_PROVIDER_TIMEOUT`, `QUOTE_STALE_AFTER_MINUTES`, `CORS_ALLOWED_ORIGINS`, and `AGENT_PLATFORM_ENCRYPTION_KEY`.
- `errors.py` is the single source for domain-level error envelopes and validation-detail shaping.
- `formatting.py` is the single place for decimal parsing, decimal string serialization, symbol/currency normalization, UTC conversion, and `utcnow()`.
- `config.py` normalizes `public_base_url`.

## ANTI-PATTERNS
- Do not read env vars directly from routes/services when `Settings` already defines them.
- Do not hand-build error envelopes or raise raw `HTTPException` for domain errors.
- Do not parse money/quantity strings or normalize symbols/currencies ad hoc in feature code.
- Do not duplicate timezone helpers outside `formatting.py`.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py
```

## NOTES
- Default CORS must allow the local Vite hosts, Playwright hosts, and anything injected by `start.sh`.
- `extra="ignore"` in settings is only for env loading; request schemas still use `extra="forbid"`.
- Current platform execution reads model/provider settings through `Settings`; service code should not access env vars directly.
