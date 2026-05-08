# E2E GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This directory owns Playwright browser coverage only.

## OVERVIEW
Playwright specs exercise the built frontend against dedicated test servers. Coverage is route-family based across smoke/navigation, preserved portfolios/templates/reports, Workflow Packages, Model Connections, Runs, and removed old global authoring routes.

## STRUCTURE
```text
e2e/
|-- smoke.spec.ts
|-- navigation.spec.ts
|-- functional.spec.ts
|-- reports.spec.ts
|-- workflow-packages.spec.ts
`-- workflow-package-tradingagents-smoke.spec.ts
```

## CONVENTIONS
- Playwright runs backend `8001` and frontend `4173` through `scripts/start-playwright-backend.mjs` and `scripts/start-playwright-frontend.mjs`.
- Specs should use API-assisted setup when it keeps the UI assertion focused.
- Preserved product setup uses `/api/v1`; platform setup uses `/api`.
- Do not add sleeps when a role, URL, response, or `expect.poll` can express readiness.
