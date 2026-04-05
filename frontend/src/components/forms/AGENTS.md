# FRONTEND FORM COMPONENTS GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/components/AGENTS.md`.

## OVERVIEW
`src/components/forms/` contains cross-route dialog forms that are reused outside a single feature page. Current coverage is portfolio create/edit and template-driven report generation.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio create/edit dialog | `portfolio-form-dialog.tsx` | react-hook-form + Zod dialog for create/update portfolio flows |
| Report generation dialog | `generate-report-dialog.tsx` | shared template selector plus runtime-input row editor |
| Focused tests | `portfolio-form-dialog.test.tsx` | dialog validation and submit behavior |

## CONVENTIONS
- Dialogs accept data and callbacks from the parent route; they do not own navigation, toasts, or network requests.
- `portfolio-form-dialog.tsx` uses `portfolioCreateFormSchema` from `../shared/form-schemas.ts` and switches between create/update payload shapes based on `initial` props.
- `generate-report-dialog.tsx` uses `runtime-inputs.ts` helpers so editor- and report-list launches share the same key/value row semantics.
- `lockTemplateSelection` exists for the template editor path; leave template choice editable when the dialog is used from the report list.

## ANTI-PATTERNS
- Do not call hooks or API modules directly from this folder; submission behavior belongs to parents.
- Do not fork runtime-input row handling away from `src/lib/runtime-inputs.ts`.
- Do not move feature-specific page layout into these dialogs just because the form fields overlap.

## VALIDATION
```bash
cd frontend
pnpm test:run src/components/forms/portfolio-form-dialog.test.tsx src/pages/templates/editor.test.tsx
```

## NOTES
- `GenerateReportDialog` resets both the selected template and runtime-input rows whenever the dialog closes or reopens.
- Portfolio slug and base currency stay immutable during edit mode; the dialog reflects that by disabling those fields when `initial` is present.
