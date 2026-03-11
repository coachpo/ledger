# Application Issues Found by E2E Testing

## Current Status
- **Application-critical issues reproduced**: 0
- **E2E infrastructure issues resolved**: 2
- **Suite status**: **17/17 passing**

## Resolved Issues

### 1. E2E Backend Startup Gap
**Status**: Resolved

#### Problem
Playwright started the frontend dev server but did not start the backend API. This caused UI flows to fail with `Failed to fetch`, which made earlier reports look like application-level defects.

#### Fix
- Added a dedicated Playwright backend startup script
- Added a dedicated Playwright frontend startup script
- Updated Playwright config to boot both services automatically
- Isolated the E2E backend database for deterministic runs
- Updated CI to install Python/backend dependencies before running E2E

### 2. Missing `test:e2e` Script
**Status**: Resolved

#### Problem
CI invoked `pnpm test:e2e`, but `frontend/package.json` did not define that script.

#### Fix
- Added `test:e2e` to frontend scripts
- Updated CI to use the now-valid self-contained E2E entrypoint

## Re-evaluated Earlier Reports

### Trading API 500
**Status**: Not reproduced

Verified with:
- backend trading API tests passing
- full Playwright suite passing against the fixed E2E environment

### Keyboard Shortcut Test
**Status**: Passing

The test passes once the suite runs against a fully started stack.

### Mobile Viewport Test
**Status**: Passing

The test passes once the suite runs against a fully started stack.

## Verification
- `cd backend && pytest tests/test_api.py -k trading -q` → **2 passed**
- `cd frontend && pnpm lint` → **passed**
- `cd frontend && pnpm build` → **passed**
- `cd frontend && pnpm test:e2e` → **17/17 passed**

## Conclusion
The issues found in the earlier markdown were rooted in incomplete E2E startup, not in broken portfolio or trading behavior. The suite is now self-contained and reproducible.
