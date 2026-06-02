# Frontend UI and UX docs

This folder owns SignalDeck frontend UI standards for shared page chrome, reusable components, and migration work. It lives under `src/components/shared` because the current frontend architecture keeps cross-feature UI in `components/shared`, shadcn primitives in `components/ui`, route shell contracts in `routes.metadata.ts` plus `layout.tsx`, and global tokens in `styles/theme.css`.

## Read these first

1. `ui-ux-standard.md`: the project standard for layout, type, theme, controls, states, accessibility, and naming.
2. `ui-library-reference.md`: developer-facing specs for the shared component library.
3. `page-blueprints.md`: examples for inventory pages, workspace/detail shells, split inspectors, and dialog form flows.
4. `migration-guide.md`: how to replace older local UI patterns without changing route ownership.

## Ownership

These docs describe frontend UI only. They don't own backend contracts, product requirements, data fetching rules, or feature-specific business logic.

Shared UI belongs in `src/components/shared` only when it has real cross-feature use. Primitive wrappers stay in `src/components/ui`. Feature-only widgets stay with their route or feature folder.
