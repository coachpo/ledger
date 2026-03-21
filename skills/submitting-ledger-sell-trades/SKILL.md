---
name: submitting-ledger-sell-trades
description: Use when submitting a SELL trading operation to the local Ledger app for an existing portfolio symbol, especially when the request is phrased as selling from a position or starts from a portfolio slug.
---

# Submitting Ledger SELL Trades

Submit SELL operations to Ledger only. A sell targets the portfolio trade endpoint; the position is resolved internally by symbol and must already exist.

## Workflow

1. **Use the live trade surface**
   - Trading writes go to `POST /api/v1/portfolios/{portfolioId}/trading-operations`.
   - Do not use `/positions` as the write surface for a sell.
   - The live trade contract lives in the backend route, schema, service, and test files below.
   - Verify against the live app files when needed: `backend/app/api/trading_operations.py`, `backend/app/schemas/trading_operation.py`, `backend/app/services/trading_operation_service.py`, and `backend/tests/test_api.py`.

2. **Resolve identifiers before POST**
   - `GET /api/v1/portfolios` → find the requested `slug`, extract numeric `id`
   - `GET /api/v1/portfolios/{portfolioId}/balances` → find the requested balance label
   - Use only balances with `operationType == "DEPOSIT"`
   - If the portfolio cannot be resolved, the balance label is missing, or multiple deposit balances fit and the user did not choose one, stop and ask for the unresolved identifier. Never auto-pick a balance.

3. **Collect required inputs**
   - `symbol` uppercase
   - `quantity` string greater than zero
   - `price` string greater than or equal to zero
   - `executedAt` timezone-aware ISO timestamp
   - `commission` optional; default to `"0"` only when the user omitted it
   - If any required field or identifier is unresolved, ask only for the missing pieces: `symbol`, portfolio resolution, deposit balance choice/`balanceId`, `quantity`, `price`, or `executedAt`.
   - Never invent required values or silently default `executedAt` to now.

4. **Run SELL preflights before POST**
   - `GET /api/v1/portfolios/{portfolioId}/positions` → find the requested symbol
   - Stop early if the position does not exist
   - Stop early if requested sell `quantity` exceeds current position quantity
   - `sellCashImpact = quantity × price - commission`
   - Chosen deposit balance must satisfy `balance.amount + sellCashImpact >= 0`
   - Explain the blocking condition instead of posting blindly

5. **POST exactly this shape**
   ```json
   {
     "side": "SELL",
     "symbol": "AAPL",
     "balanceId": 7,
     "quantity": "3",
     "price": "205.00",
     "commission": "0.50",
     "executedAt": "2026-03-19T15:00:00Z"
   }
   ```
   - External JSON is camelCase
   - Numeric wire values stay as strings
   - `executedAt` must include timezone
   - Success returns `operation`, `updatedPosition`, and `updatedBalance`
   - `updatedPosition` can be `null` on a full sell-down because Ledger deletes the position when quantity reaches zero

## Must Not Do

- Do not POST to `/positions` to represent a sell
- Do not rely on narrow workflow guides for trade endpoints
- Do not use a WITHDRAWAL balance
- Do not invent quantity, price, ids, or timestamps
- Do not auto-pick a deposit balance when the user has not clearly chosen one
- Do not default `executedAt` to "now" unless the user explicitly chose that timestamp
- Do not skip the existing-position and oversell checks

## Common Failures

| Mistake | Correct action |
| --- | --- |
| Treating a position as the write endpoint | Use `trading-operations`; the position is resolved by symbol |
| Assuming the trade can proceed without checking holdings | Read current positions and compare quantities |
| Silently filling in `executedAt` | Stop and request the timestamp |
| Matching balance by label but not type | Require `operationType == "DEPOSIT"` |

## Error Codes

- `oversell_rejected` — missing position or requested sell quantity exceeds holdings
- `invalid_operation_balance` — chosen balance is not a deposit balance
- `insufficient_balance` — selected balance would become negative after applying `quantity × price - commission`
- `not_found` — portfolio or balance id not found
- `validation_error` — malformed payload, missing, or invalid fields
