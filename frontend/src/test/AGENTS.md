# TEST SETUP GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This directory owns Vitest browser-environment setup only.

## OVERVIEW
`setup.ts` prepares jsdom for React component and hook tests. It adds Testing Library matchers plus browser API and geometry shims expected by shared UI primitives and routed components.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

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
