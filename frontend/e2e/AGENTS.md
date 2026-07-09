# Frontend E2E Guide

## Overview

Playwright specs exercise browser workflows against a disposable backend, fake OpenAI provider, scheduler worker, and production frontend preview.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| Playwright config | `playwright.config.ts` | Chromium-only, parallel, CI retry/worker behavior. |
| Backend server | `scripts/start-playwright-backend.mjs` | Disposable DB, fake provider, scheduler, uvicorn on `8001`. |
| Frontend server | `scripts/start-playwright-frontend.mjs` | Build then preview on `4173`. |
| Workflow specs | `workflow-packages.spec.ts`, `workflow-package-tradingagents-smoke.spec.ts` | Package CRUD/import/launch smoke. |
| Schedule specs | `scheduled-tasks.spec.ts` | Recurrence and run-now flows. |
| Run specs | `runs.spec.ts` | Evidence and async run polling. |

## Conventions

- Seed state through Playwright `request` against `http://127.0.0.1:8001/api` or `/api/v1`.
- Use unique names with timestamps/random suffixes and clean up created entities when practical.
- Prefer role, label, and stable `data-testid` locators over CSS structure.
- Wait on specific responses, URLs, or run-state polling instead of fixed sleeps.
- Scheduled-task specs should pin timezone with `test.use({ timezoneId: "UTC" })` when recurrence math matters.
- Backend E2E ports are `8001` for API and `18081` for fake provider; frontend preview is `4173`.

## Anti-Patterns

- Do not call real model/provider services.
- Do not make tests order-dependent or rely on seed data from another spec.
- Do not assert transient timestamps without timezone normalization.
