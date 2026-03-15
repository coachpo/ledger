# API Design

## Conventions

- Base path: `/api/v1`
- Standard format: JSON
- CSV upload endpoints use `multipart/form-data`
- IDs use numeric integers
- Decimal values serialize as strings
- Timestamps serialize as ISO 8601 UTC strings
- External field names use camelCase

## Error Envelope

```json
{
  "code": "business_rule_violation",
  "message": "Insufficient balance for buy operation",
  "details": []
}
```

## Portfolio Endpoints

### GET `/api/v1/portfolios`

Returns all portfolios.

### POST `/api/v1/portfolios`

Request:

```json
{
  "name": "Core Portfolio",
  "description": "Long-term holdings",
  "baseCurrency": "USD"
}
```

### GET `/api/v1/portfolios/{portfolioId}`

Returns one portfolio and lightweight summary metadata.

### PATCH `/api/v1/portfolios/{portfolioId}`

Request:

```json
{
  "name": "Core Portfolio",
  "description": "Updated description"
}
```

### DELETE `/api/v1/portfolios/{portfolioId}`

Deletes the portfolio and all related balances, positions, operations, stock-analysis history, and stock-analysis settings.

## Balance Endpoints

### GET `/api/v1/portfolios/{portfolioId}/balances`

Returns all balances for the portfolio.

### POST `/api/v1/portfolios/{portfolioId}/balances`

Request:

```json
{
  "label": "Cash",
  "amount": "25000.00"
}
```

### PATCH `/api/v1/portfolios/{portfolioId}/balances/{balanceId}`

Request:

```json
{
  "label": "Trading Cash",
  "amount": "22000.00"
}
```

### DELETE `/api/v1/portfolios/{portfolioId}/balances/{balanceId}`

Deletes the selected balance.

## Position Endpoints

### GET `/api/v1/portfolios/{portfolioId}/positions`

Returns all aggregate positions for the portfolio.

### POST `/api/v1/portfolios/{portfolioId}/positions`

Request:

```json
{
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "quantity": "10",
  "averageCost": "185.50"
}
```

### PATCH `/api/v1/portfolios/{portfolioId}/positions/{positionId}`

Request:

```json
{
  "quantity": "12",
  "averageCost": "184.10"
}
```

### DELETE `/api/v1/portfolios/{portfolioId}/positions/{positionId}`

Deletes the selected position.

## CSV Import Endpoints

### POST `/api/v1/portfolios/{portfolioId}/positions/imports/preview`

Content type: `multipart/form-data`

Form fields:

- `file`: CSV file

Response:

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

### POST `/api/v1/portfolios/{portfolioId}/positions/imports/commit`

Content type: `multipart/form-data`

Form fields:

- `file`: CSV file

Response:

```json
{
  "fileName": "positions.csv",
  "mode": "upsert",
  "inserted": 2,
  "updated": 1,
  "unchanged": 0,
  "errors": []
}
```

## Trading Operation Endpoints

### GET `/api/v1/portfolios/{portfolioId}/trading-operations`

Returns recent trading operations for the portfolio, newest first.

### POST `/api/v1/portfolios/{portfolioId}/trading-operations`

The request uses a discriminated union on `side`.

#### BUY request

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

#### SELL request

```json
{
  "balanceId": 12,
  "symbol": "AAPL",
  "side": "SELL",
  "quantity": "2",
  "price": "195.00",
  "commission": "1.50",
  "executedAt": "2026-03-11T14:05:00Z"
}
```

#### DIVIDEND request

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

#### SPLIT request

```json
{
  "balanceId": 12,
  "symbol": "AAPL",
  "side": "SPLIT",
  "splitRatio": "2",
  "executedAt": "2026-03-13T14:05:00Z"
}
```

Response:

```json
{
  "operation": {
    "id": 41,
    "portfolioId": 7,
    "balanceId": 12,
    "balanceLabel": "Cash",
    "symbol": "AAPL",
    "side": "BUY",
    "quantity": "5",
    "price": "190.00",
    "commission": "3.50",
    "dividendAmount": null,
    "splitRatio": null,
    "currency": "USD",
    "executedAt": "2026-03-10T14:05:00Z",
    "createdAt": "2026-03-10T14:05:01Z"
  },
  "updatedPosition": {
    "symbol": "AAPL",
    "quantity": "15",
    "averageCost": "187.23333333",
    "currency": "USD"
  },
  "updatedBalance": {
    "id": 12,
    "label": "Cash",
    "amount": "24046.50",
    "currency": "USD"
  }
}
```

Business rules:

- Reject `SELL` when quantity exceeds the current position quantity.
- Reject `BUY` when the selected balance amount is lower than the required cash impact.
- Reject `DIVIDEND` when `dividendAmount <= 0`.
- Reject `SPLIT` when no current position exists for the symbol.
- Commission is treated as an absolute amount.

## Market Data Endpoints

### GET `/api/v1/portfolios/{portfolioId}/market-data/quotes?symbols=AAPL,MSFT`

Returns delayed indicative quotes for the requested symbols in the selected portfolio context.

Behavior:

- The endpoint returns `200` with `quotes` and optional `warnings` even when some or all quotes are unavailable.
- Quotes whose provider currency does not match the portfolio base currency are omitted and returned as warnings in the current release.

Response:

```json
{
  "quotes": [
    {
      "symbol": "AAPL",
      "price": "191.24",
      "currency": "USD",
      "provider": "public_delayed_feed",
      "asOf": "2026-03-10T13:55:00Z",
      "isStale": false,
      "previousClose": "189.10"
    }
  ],
  "warnings": []
}
```

### GET `/api/v1/portfolios/{portfolioId}/market-data/history?symbols=AAPL,%5EGSPC&range=3mo`

Supported `range` values:

- `1mo`
- `3mo`
- `ytd`
- `1y`
- `max`

Response:

```json
{
  "range": "3mo",
  "interval": "1d",
  "series": [
    {
      "symbol": "AAPL",
      "currency": "USD",
      "provider": "public_delayed_feed",
      "points": [
        {
          "at": "2026-01-05T14:30:00Z",
          "close": "190.00"
        }
      ]
    }
  ],
  "warnings": []
}
```

## Stock Analysis API

### Canonical Enums

- `LlmProvider = "openai" | "anthropic" | "gemini"`
- `OpenAiEndpointMode = "chat_completions" | "responses"`
- `StockAnalysisRunType = "initial_review" | "periodic_review" | "event_review" | "manual_follow_up"`
- `StockAnalysisAction = "buy" | "add" | "hold" | "trim" | "sell" | "avoid" | "watch" | "no_action"`

### Prompt Template Endpoints

#### GET `/api/v1/stock-analysis/prompt-templates`

Returns all prompt templates.

#### POST `/api/v1/stock-analysis/prompt-templates`

Request:

```json
{
  "name": "Default Stock Review",
  "description": "Standard two-step review template",
  "freshInstructionsTemplate": "You are a senior equity analyst...",
  "freshInputTemplate": "Review {{stock.symbol}} using {{quote.summary}}",
  "compareInstructionsTemplate": "Compare the fresh analysis to prior versions...",
  "compareInputTemplate": "Latest prior version: {{version:latest.summary}}"
}
```

#### GET `/api/v1/stock-analysis/prompt-templates/{templateId}`

Returns one template.

#### PATCH `/api/v1/stock-analysis/prompt-templates/{templateId}`

Updates template content and may archive the template.

#### DELETE `/api/v1/stock-analysis/prompt-templates/{templateId}`

Delete semantics:

- Hard-delete when unused.
- Archive instead of hard-delete when historical requests depend on it.

#### POST `/api/v1/stock-analysis/prompt-templates/preview`

Previews saved or ad hoc template text at the global template-management route.

Request shape:

```json
{
  "templateId": 5,
  "step": "fresh_analysis",
  "portfolioId": 7,
  "symbol": "AAPL",
  "conversationId": null,
  "runType": "initial_review",
  "reviewTrigger": "Quarterly refresh",
  "userNote": "Focus on balance-sheet resilience",
  "freshAnalysisPayload": null,
  "instructionsTemplate": null,
  "inputTemplate": null
}
```

#### GET `/api/v1/stock-analysis/snippets`

Returns all reusable snippets.

#### POST `/api/v1/stock-analysis/snippets`

Creates a reusable snippet with `name`, unique `snippetAlias`, `content`, and optional `description`.

#### PATCH `/api/v1/stock-analysis/snippets/{snippetId}`

Updates a reusable snippet.

#### DELETE `/api/v1/stock-analysis/snippets/{snippetId}`

Deletes a reusable snippet.

Response shape:

```json
{
  "id": 9,
  "name": "Core Thesis",
  "snippetAlias": "core_thesis",
  "content": "Focus on durable free cash flow.",
  "description": "Reusable thesis framing",
  "createdAt": "2026-03-10T14:00:00Z",
  "updatedAt": "2026-03-10T14:00:00Z"
}
```

### Portfolio Stock-Analysis Endpoints

All portfolio-scoped analysis endpoints live under `/api/v1/portfolios/{portfolioId}/stock-analysis`.

#### GET `/settings`

Returns the portfolio's stock-analysis settings.

#### PATCH `/settings`

Request:

```json
{
  "enabled": true,
  "defaultPromptTemplateId": 5,

  "compareToOrigin": true
}
```

#### GET `/conversations?symbol=AAPL&include_archived=false`

Lists stock-analysis conversations for the portfolio.

#### POST `/conversations`

Request:

```json
{
  "symbol": "AAPL",
  "title": "Apple Core Thesis"
}
```

#### GET `/conversations/{conversationId}`

Returns one conversation.

#### PATCH `/conversations/{conversationId}`

Request:

```json
{
  "title": "Apple Quality Thesis",
  "isArchived": false
}
```

#### GET `/responses`

Returns response summaries for picker UIs. Supports optional `conversation_id` and `limit` query params.

#### GET `/versions?symbol=AAPL`

Lists version snapshots for the portfolio, optionally filtered by symbol.

#### GET `/versions/{versionId}`

Returns one structured version snapshot.

#### POST `/prompt-preview`

Portfolio-scoped preview endpoint for rendering prompt text against live portfolio context.

Validation rule:

- `portfolioId` in the JSON body must match the route portfolio id.

## Stock Analysis Type Surface

Canonical request and response models to keep aligned across backend and frontend:

- `PortfolioStockAnalysisSettingsRead`
- `PortfolioStockAnalysisSettingsUpdate`
- `PromptTemplateRead`
- `PromptTemplateWrite`
- `PromptTemplateUpdate`
- `PromptPreviewRequest`
- `PromptPreviewResponse`
- `StockAnalysisConversationWrite`
- `StockAnalysisConversationUpdate`
- `StockAnalysisConversationRead`
- `StockAnalysisResponseSummary`
- `StockAnalysisVersionRead`

## HTTP Status Guidelines

- `200` - successful read or update response
- `201` - successful create response
- `204` - successful delete response
- `400` - malformed file, preview mismatch, or business-rule violation
- `404` - portfolio or nested resource not found
- `422` - payload validation failure

## Notes

- CSV preview and commit stay intentionally separate.
- Trading operations are append-only historical artifacts.
- Stock-analysis history is local-first and remains readable even if provider-side retention expires.
- Multiple providers are supported across the product, but a single run selects exactly one provider config.
