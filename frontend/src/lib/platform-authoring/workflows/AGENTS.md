# FRONTEND PLATFORM AUTHORING WORKFLOWS LIB GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, `/frontend/src/lib/AGENTS.md`, and `/frontend/src/lib/platform-authoring/AGENTS.md`.

## OVERVIEW
`workflows/` owns package-local workflow graph drafts, manifest parsing/formatting, codecs, wire-binding rules, and validation helpers. It mirrors the package workflow contract for editor use without owning React state or API calls.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Workflow draft model | `types.ts`, `draft.ts` | editor-friendly graph and initial workflow draft helpers |
| Workflow codec | `codec.ts` | graph draft to backend-compatible workflow conversion |
| Manifest helpers | `manifest.ts`, `manifest.test.ts` | parse/format/outline/diagnostics for package workflow YAML |
| Validation | `validation.ts` | agent refs, slot paths, and wire-binding issue checks |

## CONVENTIONS
- Treat workflow refs as package-local keys, not database ids.
- Keep wire-binding path validation centralized so workflow-builder components do not fork slot/path semantics.
- Manifest helpers must reject unsupported YAML features consistently with backend parsers.
- Validation returns structured issues that editor panels render inline.

## ANTI-PATTERNS
- Do not add route, hook, API, toast, or navigation imports.
- Do not use workflow helpers to revive retired global `/workflows*` surfaces.
- Do not let workflow-builder UI components own parsing or backend contract conversion.

## VALIDATION
```bash
cd frontend
pnpm test:run src/lib/platform-authoring/workflows/manifest.test.ts
```
