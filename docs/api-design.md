# API Design

## Conventions

- Base path: `/api/v1`
- Format: JSON for standard endpoints, `multipart/form-data` for CSV upload endpoints.
- IDs use UUID strings.
- Decimal values are serialized as strings.
- Timestamps use ISO 8601 UTC strings.

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

Response:

```json
[
  {
    "id": "9b2b4d82-5e71-4f41-8d44-1b9d4b2712b6",
    "name": "Core Portfolio",
    "description": "Long-term holdings",
    "baseCurrency": "USD",
    "positionCount": 4,
    "balanceCount": 2,
    "createdAt": "2026-03-10T14:00:00Z",
    "updatedAt": "2026-03-10T14:00:00Z"
  }
]
```

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

Deletes the portfolio and all related balances, positions, and trading operations.

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

Response:

```json
{
  "id": "e5266f3d-f4ce-45d1-a8e2-c42ee27caa7f",
  "portfolioId": "9b2b4d82-5e71-4f41-8d44-1b9d4b2712b6",
  "label": "Cash",
  "amount": "25000.00",
  "currency": "USD",
  "createdAt": "2026-03-10T14:00:00Z",
  "updatedAt": "2026-03-10T14:00:00Z"
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

Deletes the position.

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

Request:

```json
{
  "balanceId": "e5266f3d-f4ce-45d1-a8e2-c42ee27caa7f",
  "symbol": "AAPL",
  "side": "BUY",
  "quantity": "5",
  "price": "190.00",
  "commission": "3.50",
  "executedAt": "2026-03-10T14:05:00Z"
}
```

Response:

```json
{
  "operation": {
    "id": "aab78df0-5d37-4b15-875a-4f5fa620f822",
    "portfolioId": "9b2b4d82-5e71-4f41-8d44-1b9d4b2712b6",
    "balanceId": "e5266f3d-f4ce-45d1-a8e2-c42ee27caa7f",
    "balanceLabel": "Cash",
    "symbol": "AAPL",
    "side": "BUY",
    "quantity": "5",
    "price": "190.00",
    "commission": "3.50",
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
    "id": "e5266f3d-f4ce-45d1-a8e2-c42ee27caa7f",
    "label": "Cash",
    "amount": "24046.50",
    "currency": "USD"
  }
}
```

Business rules:

- Reject `SELL` when quantity exceeds the existing position quantity.
- Reject `BUY` when the selected balance amount is lower than the required cash impact.
- Commission is treated as an absolute amount.

## Market Data Endpoints

### GET `/api/v1/portfolios/{portfolioId}/market-data/quotes?symbols=AAPL,MSFT`

Returns delayed indicative quotes for the requested symbols in the selected portfolio context.

Behavior:

- The endpoint returns `200` with `quotes` and optional `warnings` even when some or all quotes are unavailable.
- Quotes whose provider currency does not match the portfolio base currency are omitted and returned as warnings in MVP.

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
      "isStale": false
    },
    {
      "symbol": "MSFT",
      "price": "403.10",
      "currency": "USD",
      "provider": "public_delayed_feed",
      "asOf": "2026-03-10T13:50:00Z",
      "isStale": true
    }
  ],
  "warnings": []
}
```

## HTTP Status Guidelines

- `200` - successful read or update response
- `201` - successful create response
- `204` - successful delete response
- `400` - business-rule violation or malformed file
- `404` - portfolio or nested resource not found
- `422` - payload validation failure

## Notes

- CSV preview and commit are intentionally separate so the user can correct files before persistence.
- Trading operations are append-only. Corrections should happen through manual balance or position edits rather than trade mutation in MVP.
- Current balances and positions are authoritative in MVP; trading operations are not replayed to reconstruct state.
- Market data is decoupled from portfolio CRUD so quote-provider failure does not block core records.
