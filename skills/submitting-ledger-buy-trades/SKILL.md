---
name: submitting-ledger-buy-trades
description: Use when submitting a BUY trading operation to the local Ledger app for a portfolio symbol, especially when the request starts from a portfolio slug, balance label, or the narrower self_reflection workflow YAML.
---

# Submitting Ledger BUY Trades

Submit BUY operations to Ledger only. Do not create positions directly, and do not treat the self-reflection workflow OpenAPI file as the trade contract.

## Workflow

1. **Use the live trade surface**
   - Trading writes go to `POST /api/v1/portfolios/{portfolioId}/trading-operations`.
   - `docs/self_reflection_template_workflow_openapi.yaml` does not define BUY or SELL endpoints.
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
   - Never invent required values and never pretend a runtime lookup succeeded when it did not.

4. **Run BUY preflights before POST**
   - `cashImpact = quantity × price + commission`
   - Chosen balance amount must cover `cashImpact`
   - Portfolio net cash must also cover `cashImpact`: add DEPOSIT balances, subtract WITHDRAWAL balances
   - Stop early if either check fails; explain the blocking condition instead of posting blindly

5. **POST exactly this shape**
   ```json
   {
     "side": "BUY",
     "symbol": "AAPL",
     "balanceId": 7,
     "quantity": "2",
     "price": "190.25",
     "commission": "1.00",
     "executedAt": "2026-03-19T14:30:00Z"
   }
   ```
   - External JSON is camelCase
   - Numeric wire values stay as strings
   - `executedAt` must include timezone
   - Success returns `operation`, `updatedPosition`, and `updatedBalance`

## Must Not Do

- Do not POST to `/positions` to represent a buy
- Do not rely on `docs/self_reflection_template_workflow_openapi.yaml` for trade endpoints
- Do not use a WITHDRAWAL balance
- Do not invent quantity, price, ids, or timestamps
- Do not auto-pick a deposit balance when the user has not clearly chosen one
- Do not skip the portfolio-net-cash check just because the chosen balance looks large enough

## Common Failures

| Mistake | Correct action |
| --- | --- |
| Using the YAML workflow spec as the whole contract | Search the live trade route and schema files |
| Guessing missing trade economics | Stop and request only the missing fields |
| Matching balance by label but not type | Require `operationType == "DEPOSIT"` |
| Ignoring withdrawals | Compute portfolio net cash before BUY |

## Error Codes

- `invalid_operation_balance` — chosen balance is not a deposit balance
- `insufficient_balance` — chosen balance or portfolio net cash is too small
- `not_found` — portfolio or balance id not found
- `validation_error` — malformed payload, missing, or invalid fields
