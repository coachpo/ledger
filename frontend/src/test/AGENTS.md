# TEST SETUP GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This directory owns Vitest browser-environment setup only.

## OVERVIEW
`setup.ts` prepares jsdom for React component and hook tests. It adds Testing Library matchers plus browser API and geometry shims expected by shared UI primitives and routed components.

The application is under active development and has no users at the moment; future upgrade, migration, and compatibility design must account for that and should not preserve speculative legacy paths.

## STRUCTURE
```text
src/test/
`-- setup.ts
```

## CONVENTIONS
- `vite.config.ts` points Vitest `setupFiles` at `./src/test/setup.ts` and uses `jsdom`.
- `setup.ts` imports `@testing-library/jest-dom/vitest`.
- `ResizeObserver`, `matchMedia`, and `IntersectionObserver` are mocked for deterministic tests.
- HTMLElement geometry defaults to `800x400` through `offsetWidth`, `offsetHeight`, and `getBoundingClientRect()`.
- Put route-specific mocks, network mocks, and data factories in their owning tests, not global setup.
