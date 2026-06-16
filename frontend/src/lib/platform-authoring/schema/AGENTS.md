# FRONTEND PLATFORM AUTHORING SCHEMA LIB GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, `/frontend/src/lib/AGENTS.md`, and `/frontend/src/lib/platform-authoring/AGENTS.md`.

## OVERVIEW
`schema/` owns the editor-friendly schema IR, JSON Schema codec, factories, preview values, schema templates, launch-input draft state, and validation helpers used by package-local output schemas and workflow launch forms.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Schema IR | `types.ts` | editor-owned schema node/value type model |
| JSON Schema codec | `codec.ts`, `codec.test.ts` | backend wire schema to editor IR and back |
| Defaults and preview | `factories.ts`, `preview.ts`, `preview.test.ts` | initial nodes and sample payloads |
| Schema templates | `schema-template.ts`, `schema-template.test.ts` | reusable title/description defaults for generated forms |
| Launch input state | `launch-input-state.ts`, `launch-input-state.test.ts` | workflow launch parameter draft preservation and conversion |
| Validation | `validation.ts` | structured schema issue generation |

## CONVENTIONS
- Codecs own all IR/wire translation; pages and components should not reimplement JSON Schema parsing.
- Keep the supported schema subset aligned with backend compilers and tests before widening it.
- Launch input state belongs here because it mirrors schema-driven generated form behavior, not route-specific page state.
- Validation returns issues for UI rendering and should not throw for normal authoring errors.

## ANTI-PATTERNS
- Do not import React, hooks, API helpers, or route modules.
- Do not silently accept YAML/JSON Schema features the backend rejects.
- Do not fork launch-input draft conversion in workflow launch or Scheduled Task pages.

## VALIDATION
```bash
cd frontend
pnpm test:run src/lib/platform-authoring/schema/codec.test.ts src/lib/platform-authoring/schema/preview.test.ts src/lib/platform-authoring/schema/schema-template.test.ts src/lib/platform-authoring/schema/launch-input-state.test.ts
```
