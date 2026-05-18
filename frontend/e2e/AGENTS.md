# E2E GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This directory owns Playwright browser coverage only.

## OVERVIEW
Playwright specs exercise the built frontend against dedicated test servers. Coverage is route-family based across smoke/navigation, preserved portfolios/templates/reports, Extensions, Workflow Packages, Model Connections, Runs, and guards for retired legacy global authoring routes, hidden legacy nav entries, and `/templates/seed`.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

## STRUCTURE
```text
e2e/
|-- smoke.spec.ts
|-- navigation.spec.ts
|-- functional.spec.ts
|-- reports.spec.ts
|-- extensions.spec.ts
|-- workflow-packages.spec.ts
`-- workflow-package-tradingagents-smoke.spec.ts
```

## CONVENTIONS
- Playwright runs backend `8001` and frontend `4173` through `scripts/start-playwright-backend.mjs` and `scripts/start-playwright-frontend.mjs`.
- Specs should use API-assisted setup when it keeps the UI assertion focused.
- Preserved product setup uses `/api/v1`; platform setup uses `/api`.
- Use role/text/testid locators and web-first assertions; avoid brittle deep CSS, XPath, and `nth-child` chains.
- For ordinary removal-only browser validation, prefer manual confirmation over adding dedicated “proves not” Playwright specs unless the absence itself is a shipped contract or route guard.
- Do not add sleeps when a role, URL, response, or `expect.poll` can express readiness.
