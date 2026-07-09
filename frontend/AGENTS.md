# Frontend Guide

## Overview

The frontend is a React 19/Vite management UI using TanStack Query, React Router, shadcn/Radix primitives, semantic Tailwind tokens, Vitest, and Playwright.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| App routes | `src/routes.ts` | Browser route families and layout ownership. |
| Design system | `DESIGN.md`, `src/styles/theme.css` | Tokens, shells, surface model, component rules. |
| API client | `src/lib/api-client.ts` | `/api/v1` and `/api` request helpers, token retry, safe errors. |
| Query keys | `src/lib/query-keys.ts` | Canonical TanStack Query key registry. |
| Data hooks | `src/hooks/` | Query/mutation boundary and invalidation behavior. |
| UI primitives | `src/components/ui/` | Presentational shadcn/Radix wrappers only. |
| Shared chrome | `src/components/shared/` | Page shells, tables, dialogs, states, status chrome. |
| E2E | `e2e/` | Cross-stack browser specs. |

## Conventions

- Follow `DESIGN.md`: compact management UI, semantic tokens, `shadow-ui-*`, no route-local themes or decorative variants.
- Inventory routes use `InventoryPageShell`; full-height editors and consoles use `WorkspacePageShell`.
- Feature pages own copy, route params, hooks, mutations, toasts, navigation, sorting, and validation.
- Shared components stay presentational and reusable. Do not put route/API/domain logic in `components/ui`.
- API files call `request` for `/api/v1` extension surfaces and `requestPlatform` for platform `/api` surfaces.
- Hooks use `queryKeys`, guard optional IDs with `enabled`, and invalidate every affected list/detail/related scope.
- Browser-visible API types mirror external camelCase contracts; secret-like values are write-only or represented by safe presence fields.
- React Hooks recommended lint rules stay enabled without local downgrades, including `react-hooks/set-state-in-effect`.

## Commands

```bash
pnpm lint
pnpm typecheck
pnpm build
pnpm test:run
pnpm exec playwright install --with-deps chromium
pnpm test:e2e
```

## Anti-Patterns

- Do not add new UI libraries, styling frameworks, token files, or route-local visual systems.
- Do not hand-roll query key arrays.
- Do not use regex/string hacks for Workflow Package YAML or schema/value transformation when structured helpers exist.
- Do not render raw secret values, unsafe API error details, or provider internals.
