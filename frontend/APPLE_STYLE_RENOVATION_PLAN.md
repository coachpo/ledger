# Apple-Style Renovation Plan

## Current Visual Problems

- The universal component foundation exists, but many surfaces still read as default shadcn admin chrome: small `rounded-md` controls, hard borders, sparse shadows, and muted panels without a coherent elevation model.
- The app shell is functional but plain. Sidebar, top bar, breadcrumbs, and mobile drawer need calmer Apple-inspired surfaces, softer active states, clearer focus, and more precise spacing.
- Shared inventory/workspace shells use consistent structure, but the default padding, toolbar treatment, filter bars, table frames, and state panels are visually thin.
- Route-local console/detail pages still contain many hand-rolled `rounded-* border bg-muted/*` panels, dashed empty containers, `space-y-*` stacks, and one-off card treatments.
- Tables rely heavily on borders and muted header rows. They need softer containment, clearer header hierarchy, stable row hover/selected states, and refined pagination.
- Dialogs and overlays use default border/shadow density. Entity dialogs need a more polished grouped-surface model while preserving Radix behavior.

## Apple-Inspired Target Language

- Content-first management UI with restrained chrome, subtle separators, grouped surfaces, soft depth, and precise alignment.
- Neutral light theme based on system-style backgrounds, clean white/elevated surfaces, graphite text, a single blue-violet accent, and restrained semantic colors.
- Dark theme remains first-class with low-glare surfaces, visible separators, and the same interaction hierarchy.
- Typography uses the existing system font stack, with improved rhythm for headings, labels, captions, tables, code, and numeric text. Do not bundle or reference Apple proprietary fonts.
- Data density stays practical. Tables and console evidence remain efficient and scannable instead of being turned into decorative card grids.
- Motion stays restrained: tokenized 150-300ms color, shadow, transform, and opacity transitions; no decorative animation.

## Token Changes

- Refine `src/styles/theme.css` as the single token source of truth.
- Add Apple-style surface tokens: canvas, surface, surface elevated, surface grouped, surface inset, separator, text secondary, text tertiary, accent soft, and focus shadow.
- Add layout/control tokens for sidebar width, app header height, page padding, page gutters, table row height, dialog width, modal inset, toolbar height, and filter height.
- Refine shadow tokens to softer layered elevation and keep dark-mode counterparts.
- Add radius tokens for small controls, grouped panels, popovers, and dialogs while keeping Tailwind semantic radius aliases.
- Add global reduced-motion handling and consistent selection/focus treatment.

## Component Changes

- App shell: polish `Layout`, `Sidebar`, and top header with grouped shell surfaces, softer active nav, refined brand mark, stable header height, and accessible skip link.
- Primitives: update `Button`, `Input`, `Textarea`, `Select`, `Card`, `Table`, `Tabs`, `Badge`, `Dialog`, `Sheet`, popovers, dropdowns, skeleton, and alert wrappers to use shared tokens.
- Shared shells: update `InventoryPageShell`, `WorkspacePageShell`, `SplitInspectorLayout`, `PageContextBar`, `ResourceToolbar`, `ResourceFilterBar`, `ResourceTableFrame`, `DataTable`, `EntityDialogShell`, and state panels.
- States: standardize loading, empty, filtered-empty, error, inline notice, disabled, and dashed states so they feel intentional in light and dark themes.
- Route-local pages: migrate only presentational wrappers where obvious, especially run detail sections, scheduled-task console panels, workflow package launch/editor panels, report detail, template editor, memory admin panels, and model-connection feedback blocks.

## Migration Order

1. Global tokens, typography, motion, and base surfaces.
2. App shell and navigation.
3. UI primitives.
4. Shared inventory/workspace shells and state/table/toolbar/dialog helpers.
5. High-traffic route-local console/detail panels.
6. Documentation and deprecated pattern mapping.
7. Lint, typecheck, unit tests, build, and browser visual QA.

## Risky Pages

- `src/pages/runs/detail.tsx` and `src/pages/runs/detail-sections/**`: dense evidence panes, URL state, React Flow lineage, fork/rerun affordances, and wide payloads.
- `src/pages/scheduled-tasks/detail.tsx`: large console with JSON templates, recurrence controls, fire history, and run-now actions.
- `src/pages/workflow-packages/launch.tsx` and `editor*.tsx`: full-height editors, preflight states, saved runtime inputs, validation details, and secret bindings.
- `src/pages/templates/editor.tsx`: split markdown editor and preview layout with full-height constraints.
- `src/pages/memory/admin-components.tsx`: route-owned admin browse/detail cards, dialogs, JSON blocks, and tabs.
- `src/pages/reports/detail.tsx`: editable markdown, prose rendering, and download/edit/save controls.

## Deprecated Visual Patterns

- New route-local `rounded-md border bg-muted/20` panels for major page sections. Prefer shared `Card`, `ResourceTableFrame`, `InlineStatePanel`, or a documented route-owned section component.
- New `border-dashed` empty containers outside shared state panels.
- New `space-y-*` layout stacks in shared UI. Prefer `flex flex-col gap-*`.
- Raw color utility families such as `bg-blue-*`, `text-emerald-*`, or `border-red-*` for product UI. Prefer semantic tokens and shared status components.
- One-off shadows such as `shadow-sm`, `shadow-md`, or `shadow-lg` in route surfaces. Prefer `--ui-shadow-*` tokens or primitive variants.
- Placeholder-only labels for search, filter, and form controls.
- Pointer-only row/card click targets. Use explicit links and buttons.

## Before/After Checklist

- App shell: sidebar, header, breadcrumbs, nav active state, mobile drawer, and theme toggle share the same surface/elevation language.
- Pages: inventory, detail, editor, console, and system-state routes use consistent margins, page headers, toolbars, filters, state panels, and content containers.
- Primitives: buttons, inputs, selects, tabs, cards, badges, tables, dialogs, sheets, dropdowns, and skeletons use semantic tokens and consistent motion/focus.
- States: loading, empty, error, disabled, filtered-empty, and inline notices are visible, readable, and aligned in light and dark modes.
- Tables: headers, rows, hover/selected states, empty rows, pagination, and row actions are scannable without heavy boxes.
- Accessibility: visible focus, keyboard-safe controls, labels, contrast, non-color status cues, and reduced-motion behavior remain intact.

## Validation Commands

```bash
pnpm lint
pnpm typecheck
pnpm test:run
pnpm build
pnpm test:e2e
```

Browser visual QA should cover desktop and mobile for dashboard, Workflow Packages list/editor/launch, Scheduled Tasks detail, Runs list/detail, Memory list/detail, Model Connections editor, Reports detail, Templates editor, Portfolios list/detail, and Extensions.

## Completion Notes

- Global tokens, typography, primitive wrappers, app shell, shared route shells, tables, toolbars, filters, dialogs, state panels, and high-traffic route-local panels now use the renovated grouped/elevated surface model.
- Source scan result: no obsolete `border-dashed`, `rounded-md border bg-muted/*`, `bg-muted/20`, `bg-muted/30`, `bg-background/60`, route-surface `shadow-sm`/`shadow-md`/`shadow-lg`, or shared `space-y-*` patterns remain in TSX page/component chrome. The remaining `border-dashed` occurrence is the chart tooltip marker in `src/components/ui/chart.tsx`, which is an intentional data-visualization affordance.
- In-app Browser was unavailable for this thread (`iab` browser not available), so visual QA used the Playwright CLI fallback against the production preview.
- Browser QA used mocked read-only API responses because the preview build had no backend running. Checked Workflow Packages desktop, Runs desktop and mobile, and Memory Admin desktop for blank screens, visible console errors, control wrapping, empty states, and obvious text overlap. Console was clean after mocked routes.

## Remaining Blockers Log

- None.
