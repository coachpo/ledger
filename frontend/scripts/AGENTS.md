# PLAYWRIGHT SCRIPTS GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This directory owns E2E startup helpers only.

## OVERVIEW
These scripts are web-server commands used by `playwright.config.ts`. They start a dedicated backend and built frontend on fixed ports, forward logs through inherited stdio, and terminate child processes on shutdown signals.

The application is under active development and has no users at the moment; future upgrade, migration, and compatibility design must account for that and should not preserve speculative legacy paths.

## STRUCTURE
```text
scripts/
|-- start-playwright-backend.mjs
`-- start-playwright-frontend.mjs
```

## CONVENTIONS
- Backend startup runs from `backend/` with `uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8001`.
- The backend helper sets `QUOTE_PROVIDER_BACKEND=deterministic` unless already provided.
- Frontend startup builds first with `npx vite build`, then previews on `127.0.0.1:4173` with `--strictPort`.
- The frontend helper derives `VITE_API_BASE_URL` from env or defaults to `http://127.0.0.1:8001/api/v1`.
- Do not add fallback ports here; Playwright expects fixed ports.
