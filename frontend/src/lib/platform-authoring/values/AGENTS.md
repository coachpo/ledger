# FRONTEND PLATFORM AUTHORING VALUES LIB GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, `/frontend/src/lib/AGENTS.md`, and `/frontend/src/lib/platform-authoring/AGENTS.md`.

## OVERVIEW
`values/` owns the generated-form value-entry model used by schema-driven package authoring UIs. It converts between editor-friendly value entries and JSON-compatible values, supplies defaults, and validates draft values against schema intent.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Value model | `types.ts` | value-entry types shared by generated forms |
| Value codec | `codec.ts` | JSON-compatible value to editor entry conversion |
| Defaults | `factories.ts` | initial entries for generated forms |
| Validation | `validation.ts` | value-level issue checks |

## CONVENTIONS
- Keep values pure and serializable; React form components consume these helpers but do not own their semantics.
- Preserve JSON types when converting exact values; avoid stringifying structured values for convenience.
- Validation should explain editable field problems as issues, not exceptions.
- Keep changes aligned with `schema/` helpers and generated-form component tests.

## ANTI-PATTERNS
- Do not import UI components, hooks, API modules, or router state.
- Do not add display-only form labels to the value model.
- Do not make value codecs aware of package ids, workflow ids, or backend routes.

## VALIDATION
```bash
cd frontend
pnpm test:run src/components/platform-authoring/generated-form/schema-form.test.tsx
```
