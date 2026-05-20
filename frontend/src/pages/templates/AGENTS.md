# FRONTEND TEMPLATES PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/templates/` owns the stored-template route family: the inventory page for search, cards/table switching, and destructive delete flow, plus the full-height editor route for markdown authoring, inline compile preview, placeholder browsing, runtime input rows, formatting, and saved-template report generation.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Template inventory | `list.tsx` | search, cards/table toggle, destructive delete confirmation, and editor navigation |
| Template editor | `editor.tsx` | full-height markdown editor, inline compile preview, placeholder browser, runtime inputs, format, save, and Generate Report handoff |
| Supporting hooks | `../../hooks/use-templates.ts`, `../../hooks/use-reports.ts`, `../../hooks/use-debounce.ts` | CRUD, inline compile, placeholder tree, report generation, and preview debounce |
| Supporting components | `../../components/templates/AGENTS.md`, `../../components/forms/generate-report-dialog.tsx` | placeholder reference, runtime-input sections, and shared report-generation dialog |
| Route coverage | `editor.test.tsx` | editor save, preview, runtime-input, and report-generation route behavior |

## CONVENTIONS
- `list.tsx` owns search text, view mode, and delete confirmation state; request policy stays in hooks.
- `editor.tsx` stays route-owned and full-height; inline preview uses `useDebounce()` plus `useCompileInline()` instead of moving debounce or compile orchestration into shared components.
- Runtime input rows use `src/lib/runtime-inputs.ts` and stay aligned with `GenerateReportDialog`; do not fork row semantics between preview and report generation.
- Generate Report is a saved-template flow only. Keep it behind the shared dialog plus `useCompileReport()` instead of ad-hoc page fetch logic.
- Placeholder browsing, exact JSON preview, and markdown formatting stay in shared helpers/components; the page composes them but does not reimplement their parsing or serialization logic.

## ANTI-PATTERNS
- Do not call template or report API helpers directly from these pages.
- Do not move inline preview debounce into the hook or component layers.
- Do not fork runtime-input map/row translation away from `src/lib/runtime-inputs.ts`.
- Do not let unsaved templates generate reports or bypass the full-height editor contract.

## VALIDATION
```bash
cd frontend
pnpm test:run src/pages/templates/editor.test.tsx
```

## NOTES
- `editor.tsx` handles both `/templates/new` and `/templates/:templateId/edit`.
- Closing the editor returns to `/templates`; `Layout` provides the full-height outlet treatment for this route family.
