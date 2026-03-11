# Resolved Investigation: Trading API 500 Report

## Current Status
- **Resolved**
- **Severity**: Not an application bug
- **Outcome**: The previously reported trading API 500 was a false positive caused by E2E infrastructure, not by the backend trading endpoint.

## What Was Verified
1. Backend trading API contract tests pass:
   - `cd backend && pytest tests/test_api.py -k trading -q`
   - Result: **2 passed**
2. Full Playwright E2E suite passes when the app stack is started correctly:
   - `cd frontend && pnpm test:e2e`
   - Result: **17/17 passed**

## Root Cause
The original report came from Playwright runs that started only the frontend dev server.

- The frontend API client targets a backend URL.
- `frontend/playwright.config.ts` did **not** start the backend.
- `frontend/package.json` did **not** define the `test:e2e` script that CI expected.
- When the backend was missing, UI actions failed with `Failed to fetch`, which was then misinterpreted as a backend trading API 500.

## Fix Applied
1. Added `frontend/scripts/start-playwright-backend.mjs`
   - Starts a dedicated backend for E2E on port `8001`
   - Uses an isolated SQLite database for deterministic runs
2. Added `frontend/scripts/start-playwright-frontend.mjs`
   - Starts Vite for E2E on port `4173`
   - Points the frontend at the dedicated E2E backend
3. Updated `frontend/playwright.config.ts`
   - Uses Playwright `webServer` entries for both backend and frontend
   - Removes the hidden dependency on a manually running backend
4. Added `frontend/package.json` script:
   - `test:e2e: playwright test`

## Conclusion
The trading endpoint is working as designed. The failure signal came from incomplete test startup, not from backend trading logic.
