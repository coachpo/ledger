# API Design

> Status: Current live-code reference as of 2026-03-18 (`c175a98`).

## Conventions

- Base path: `/api/v1`
- Health path: `/health`
- Standard format: JSON
- CSV upload endpoints use `multipart/form-data`
- IDs use numeric integers
- Decimal values serialize as strings
- Timestamps serialize as ISO 8601 UTC strings with `Z`
- External field names use camelCase

## Error Envelope

```json
{
  "code": "business_rule_violation",
  "message": "Insufficient balance for buy operation",
  "details": []
}
```

Common business-rule codes include `duplicate_portfolio_slug`, `duplicate_balance_label`, `duplicate_symbol`, `insufficient_balance`, `oversell_rejected`, `balance_operation_type_locked`, `duplicate_template_name`, `invalid_slug`, `slug_conflict`, `invalid_file_type`, `invalid_file_encoding`, `file_too_large`, and `empty_file`.

## Health

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | Returns `{"status":"ok"}` |

## Portfolios

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/portfolios` | List all portfolios with summary counts |
| `POST` | `/api/v1/portfolios` | Create portfolio |
| `GET` | `/api/v1/portfolios/{portfolioId}` | Read one portfolio |
| `PATCH` | `/api/v1/portfolios/{portfolioId}` | Update `name` and `description` only |
| `DELETE` | `/api/v1/portfolios/{portfolioId}` | Delete portfolio and cascaded child data |

Create request example:

```json
{
  "name": "Retirement",
  "slug": "retirement",
  "description": "Long-term holdings",
  "baseCurrency": "USD"
}
```

## Balances

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/portfolios/{portfolioId}/balances` | List balances for the portfolio |
| `POST` | `/api/v1/portfolios/{portfolioId}/balances` | Create balance |
| `PATCH` | `/api/v1/portfolios/{portfolioId}/balances/{balanceId}` | Update label, amount, or operation type |
| `DELETE` | `/api/v1/portfolios/{portfolioId}/balances/{balanceId}` | Delete balance |

Create request example:

```json
{
  "label": "Broker Cash",
  "amount": "25000.00",
  "operationType": "DEPOSIT"
}
```

Notes:

- `operationType` is `DEPOSIT` or `WITHDRAWAL`.
- A balance with trading history cannot change `operationType`.
- Balance responses include `hasTradingOperations` so the UI can show safer affordances.

## Positions

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/portfolios/{portfolioId}/positions` | List aggregate positions |
| `POST` | `/api/v1/portfolios/{portfolioId}/positions` | Create position |
| `GET` | `/api/v1/portfolios/{portfolioId}/positions/lookup?symbol=AAPL` | Resolve optional company name |
| `PATCH` | `/api/v1/portfolios/{portfolioId}/positions/{positionId}` | Update name, quantity, or average cost |
| `DELETE` | `/api/v1/portfolios/{portfolioId}/positions/{positionId}` | Delete position |

Create request example:

```json
{
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "quantity": "10",
  "averageCost": "185.50"
}
```

Lookup response example:

```json
{
  "symbol": "AAPL",
  "name": "Apple Inc."
}
```

Notes:

- Symbols normalize to uppercase.
- If `name` is omitted during create, the backend may fill it from the symbol lookup cache/provider.

## Position CSV Import

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/v1/portfolios/{portfolioId}/positions/imports/preview` | Validate file and return accepted rows plus row errors |
| `POST` | `/api/v1/portfolios/{portfolioId}/positions/imports/commit` | Revalidate and atomically apply upserts |

Upload contract:

- Content type: `multipart/form-data`
- Form field: `file`
- Required headers: `symbol`, `quantity`, `average_cost`
- Optional header: `name`

Preview response example:

```json
{
  "fileName": "positions.csv",
  "mode": "upsert",
  "acceptedRows": [
    {
      "row": 2,
      "symbol": "AAPL",
      "quantity": "10",
      "averageCost": "185.50",
      "name": "Apple Inc."
    }
  ],
  "errors": [
    {
      "row": 3,
      "field": "quantity",
      "issue": "Must be greater than zero"
    }
  ]
}
```

## Trading Operations

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/portfolios/{portfolioId}/trading-operations` | List operations, newest first |
| `POST` | `/api/v1/portfolios/{portfolioId}/trading-operations` | Create one operation via discriminated union on `side` |

`BUY` example:

```json
{
  "balanceId": 12,
  "symbol": "AAPL",
  "side": "BUY",
  "quantity": "5",
  "price": "190.00",
  "commission": "3.50",
  "executedAt": "2026-03-10T14:05:00Z"
}
```

`DIVIDEND` example:

```json
{
  "balanceId": 12,
  "symbol": "AAPL",
  "side": "DIVIDEND",
  "dividendAmount": "25.00",
  "commission": "0.50",
  "executedAt": "2026-03-12T14:05:00Z"
}
```

`SPLIT` example:

```json
{
  "symbol": "AAPL",
  "side": "SPLIT",
  "splitRatio": "2",
  "executedAt": "2026-03-13T14:05:00Z"
}
```

Response shape:

```json
{
  "operation": { "id": 41, "side": "BUY", "symbol": "AAPL" },
  "updatedPosition": { "symbol": "AAPL", "quantity": "15", "averageCost": "187.23333333", "currency": "USD" },
  "updatedBalance": { "id": 12, "label": "Broker Cash", "amount": "24046.50", "currency": "USD" }
}
```

Business rules:

- `BUY`, `SELL`, and `DIVIDEND` require a deposit balance.
- `BUY` rejects insufficient selected-balance cash and insufficient portfolio cash after withdrawals.
- `SELL` rejects oversell.
- `DIVIDEND` and `SPLIT` require an existing position.
- `SPLIT` does not return an updated balance because no cash changes.

## Market Data

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/portfolios/{portfolioId}/market-data/quotes?symbols=AAPL,MSFT` | Delayed quotes plus warnings |
| `GET` | `/api/v1/portfolios/{portfolioId}/market-data/history?symbols=AAPL,%5EGSPC&range=3mo` | History series plus warnings |

Quote response example:

```json
{
  "quotes": [
    {
      "symbol": "AAPL",
      "name": "Apple Inc.",
      "price": "191.24",
      "currency": "USD",
      "provider": "yahoo_finance",
      "asOf": "2026-03-10T13:55:00Z",
      "isStale": false,
      "previousClose": "189.10"
    }
  ],
  "warnings": []
}
```

History ranges:

- `1mo`
- `3mo`
- `ytd`
- `1y`
- `max`

Notes:

- The endpoint returns `200` even when some symbols degrade to warnings.
- Cached quote fallback is allowed when the live quote fetch fails.
- Currency mismatch suppresses the quote and returns a warning.

## Templates

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/templates` | List templates |
| `POST` | `/api/v1/templates` | Create template |
| `GET` | `/api/v1/templates/placeholders` | List live placeholder tree |
| `POST` | `/api/v1/templates/compile` | Inline compile ad hoc content |
| `GET` | `/api/v1/templates/{templateId}` | Read one template |
| `PATCH` | `/api/v1/templates/{templateId}` | Update template |
| `DELETE` | `/api/v1/templates/{templateId}` | Delete template |
| `GET` | `/api/v1/templates/{templateId}/compile` | Compile stored template content |
| `POST` | `/api/v1/templates/{templateId}/compile` | Compile stored template content with runtime inputs |

Create request example:

```json
{
  "name": "Morning Summary",
  "content": "Slug: {{portfolios.retirement.slug}}\nBalance: {{portfolios.retirement.balance.amount}}"
}
```

Inline compile request example:

```json
{
  "content": "Ticker: {{inputs.ticker}}\nQuantity: {{portfolios.by_slug(inputs.portfolio_slug).positions.by_symbol(inputs.ticker).quantity}}",
  "inputs": {
    "ticker": "AAPL",
    "portfolio_slug": "retirement"
  }
}
```

Inline compile response example:

```json
{
  "compiled": "Apple name: Apple Inc."
}
```

Placeholder tree response sketch:

```json
{
  "portfolios": [
    {
      "slug": "retirement",
      "name": "Retirement",
      "baseCurrency": "USD",
      "positions": [{ "symbol": "AAPL", "name": "Apple Inc." }]
    }
  ],
  "reports": [
    {
      "name": "monthly_report_20260318_105651",
      "createdAt": "2026-03-18T10:56:51Z"
    }
  ]
}
```

Notes:

- Placeholder resolution is permissive: unknown roots, slugs, symbols, or fields render explicit sentinel text rather than returning a validation error.
- Supported live namespaces start at `inputs`, `portfolios`, and `reports`.
- `reports.<name>.content` re-compiles stored report markdown and returns `[Circular report reference: ...]` if a report chain loops.
- Runtime inputs are available as `inputs.<name>` and may be used directly or inside selector arguments.
- Dynamic portfolio selectors are supported in template content: `portfolios.by_slug(...)` and `portfolios.by_slug(...).positions.by_symbol(...)`.
- Dynamic report selectors are supported in template content: `reports.latest`, `reports.latest("TICKER")`, `reports[index]`, and `reports.by_tag("tag").latest`.
- Dynamic report selectors may consume runtime inputs, for example `reports.latest(inputs.ticker)` or `reports.by_tag(inputs.analysis_tag).latest`.
- Dynamic report selectors may be followed by `.name`, `.created_at`, or `.content` after selecting a single report.
- Missing runtime inputs render explicit sentinel text such as `[Missing input: ticker]`.
- Valid dynamic selectors that match no report render an empty string.
- Malformed dynamic selectors render `[Invalid report selector: ...]`.

## Reports

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/reports` | List reports, newest first, with optional filters |
| `POST` | `/api/v1/reports` | Create an external report from JSON |
| `POST` | `/api/v1/reports/compile/{templateId}` | Compile a stored template into a persisted report |
| `POST` | `/api/v1/reports/upload` | Upload UTF-8 markdown as a report |
| `GET` | `/api/v1/reports/{slug}` | Read one report by slug |
| `PATCH` | `/api/v1/reports/{slug}` | Update report `content` only |
| `DELETE` | `/api/v1/reports/{slug}` | Delete a report |
| `GET` | `/api/v1/reports/{slug}/download` | Download stored markdown by slug |

Compiled report response example:

```json
{
  "id": 7,
  "name": "monthly_report_20260318_105651",
  "slug": "monthly_report_20260318_105651",
  "source": "compiled",
  "content": "# Report\n\nSlug: retirement",
  "metadata": {
    "author": null,
    "description": null,
    "tags": []
  },
  "createdAt": "2026-03-18T10:56:51Z",
  "updatedAt": "2026-03-18T10:56:51Z"
}
```

Direct create request example:

```json
{
  "name": "AAPL Weekly Reflection",
  "content": "# AAPL\n\nReview body.",
  "metadata": {
    "tags": ["weekly_review"],
    "analysis": {
      "ticker": "AAPL",
      "reviewType": "weekly_review"
    },
    "customFlag": true
  }
}
```

Compile-with-metadata request example:

```json
{
  "metadata": {
    "tags": ["weekly_review"],
    "analysis": {
      "ticker": "AAPL",
      "portfolioSlug": "core_us"
    }
  },
  "inputs": {
    "ticker": "AAPL",
    "portfolio_slug": "core_us",
    "analysis_tag": "analysis_result"
  }
}
```

Upload request sketch:

```text
POST /api/v1/reports/upload
Content-Type: multipart/form-data

file=<markdown .md>
slug=quarterly_update
author=Analyst
description=Uploaded from disk
tags=quarterly,finance
```

Notes:

- Compiled reports derive `name` and `slug` from the source template name plus a UTC timestamp; collisions append `_2`, `_3`, and so on.
- Direct JSON-created reports persist `source="external"`, require `content`, accept optional `name`, optional `slug`, and extensible `metadata`, and normalize analysis tickers to uppercase when present.
- Compiled report creation accepts an optional JSON body with `metadata` and runtime `inputs`.
- Uploaded reports normalize the provided slug, fall back to the uploaded filename stem when `slug` is omitted, reject invalid file types/encodings, enforce a 2 MB limit, and persist `source="uploaded"`.
- Report metadata is extensible JSON. The known fields are `author`, `description`, `tags`, and optional `analysis`, but unknown keys are preserved.
- `GET /api/v1/reports` accepts optional query parameters: `ticker`, `tag`, `reviewType`, `portfolioSlug`, `source`, `limit`, and `offset`.
- `ticker` is trimmed and matched against normalized uppercase `metadata.analysis.ticker` values.
- `tag` is trimmed and matches membership inside the top-level `metadata.tags` array.
- `reviewType` and `portfolioSlug` are trimmed exact-string matches against `metadata.analysis.reviewType` and `metadata.analysis.portfolioSlug`.
- Report lists remain ordered by `createdAt DESC, id DESC` whether filters are applied or not.
- Report updates are content-only; `name`, `slug`, `source`, and metadata are immutable after creation.
- Downloads return `text/markdown; charset=utf-8` with `Content-Disposition: attachment; filename="{slug}.md"`.

## HTTP Status Guidelines

- `200` - successful read, update, or template compile response
- `201` - successful create response, including report compile/upload
- `204` - successful delete response
- `400` - malformed file or business-rule violation
- `409` - report slug conflict on upload
- `404` - requested resource not found
- `422` - payload validation failure
