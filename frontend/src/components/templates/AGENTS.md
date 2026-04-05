# FRONTEND TEMPLATE COMPONENTS GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/components/AGENTS.md`.

## OVERVIEW
`src/components/templates/` contains template-editor support widgets: placeholder browsing, grouped placeholder display, and inline runtime-input controls.

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
