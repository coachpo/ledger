# FRONTEND FORMS GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/components/AGENTS.md`.

## OVERVIEW
`src/components/forms/` owns small cross-route dialog/form helpers: portfolio identity edits, report generation/upload dialogs, and write-only secret input UI. These components are reusable surfaces supplied with data and callbacks by their parent routes; they do not own navigation, toasts, query hooks, or direct API calls.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio dialog | `portfolio-form-dialog.tsx` | create/edit portfolio identity fields and slug/base-currency form schema |
| Report generation | `generate-report-dialog.tsx` | template selection plus runtime input rows for report compilation |
| Report upload | `report-upload-dialog.tsx` | markdown upload metadata dialog |
| Secret input | `secret-input.tsx` | write-only credential input display and rotation affordance |
| Coverage | `portfolio-form-dialog.test.tsx`, `report-upload-dialog.test.tsx` | dialog reset, submit payloads, upload behavior |

## CONVENTIONS
- Parents own mutations, toasts, route transitions, and query invalidation; form helpers emit typed payloads only.
- Dialogs reset local form state when opened/closed so stale draft data does not leak between parents.
- Report generation uses shared runtime-input row helpers from `src/lib/runtime-inputs.ts`; do not fork key/value row conversion here.
- `SecretInput` must never render stored secret values. Blank edit submissions preserve the stored backend secret through the parent route flow.
- Keep validation schemas close to the small form surface unless they become shared route contracts.

## ANTI-PATTERNS
- Do not call `fetch`, `useQuery`, `useMutation`, `toast`, or router navigation from these helpers.
- Do not move feature-specific portfolio sections, trading flows, or template-editor panels into this folder.
- Do not expose saved model-connection secrets for convenience in tests or placeholders.

## VALIDATION
```bash
cd frontend
pnpm test:run src/components/forms/portfolio-form-dialog.test.tsx src/components/forms/report-upload-dialog.test.tsx
```
