# FRONTEND TEMPLATE COMPONENTS GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/components/AGENTS.md`.

## OVERVIEW
`src/components/templates/` contains template-editor support widgets: placeholder browsing, grouped placeholder display, and inline runtime-input controls.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Placeholder browser shell | `template-placeholder-reference.tsx` | mixes static guidance groups with live backend placeholder data |
| Placeholder grouping UI | `placeholder-group.tsx` | collapsible placeholder lists with click-to-insert behavior |
| Runtime-input controls | `template-runtime-inputs-section.tsx` | inline editor rows for `inputs.*` values |
| Focused test coverage | `template-placeholder-reference.test.tsx` | placeholder browser rendering behavior |

## CONVENTIONS
- These components stay presentation-focused; the page owns compile mutations, save actions, and navigation.
- `template-placeholder-reference.tsx` combines static placeholder guidance with live `placeholderTree` data from `GET /templates/placeholders`.
- Placeholder clicks always hand raw placeholder paths back to the parent, which inserts `{{path}}` into the editor.
- `template-runtime-inputs-section.tsx` uses `RuntimeInputRow` from `src/lib/runtime-inputs.ts`; keep row ids and trim rules centralized there.

## ANTI-PATTERNS
- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not hard-code backend placeholder responses into these components; only the static guidance groups belong here.
- Do not move compile/network logic into this folder.
- Do not repurpose these widgets as generic shared inputs unless another feature truly reuses the same placeholder/runtime-input contract.

## VALIDATION
```bash
cd frontend
pnpm test:run src/components/templates/template-placeholder-reference.test.tsx src/pages/templates/editor.test.tsx
```

## NOTES
- Static guidance covers both exact placeholder paths and dynamic selectors like `reports.latest(inputs.ticker)` and `portfolios.by_slug(inputs.portfolio_slug)`.
- The runtime-inputs section stays visible whenever rows exist, even if the user collapses it, so active parameters are hard to miss.
