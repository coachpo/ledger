# FRONTEND PLATFORM AUTHORING COMMON LIB GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, `/frontend/src/lib/AGENTS.md`, and `/frontend/src/lib/platform-authoring/AGENTS.md`.

## OVERVIEW
`common/` owns pure helper contracts shared by package-local authoring codecs: resource refs, field paths, issue text, and safe JSON serialization. Nothing here knows React, routes, hooks, API helpers, or backend request paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Resource refs | `resource-ref.ts`, `resource-ref.test.ts` | canonical parse/format helpers for package-local resource references |
| Field paths | `field-path.ts` | path formatting for schema/workflow validation issues |
| Issue text | `issues.ts` | shared issue shape/text helpers for authoring validators |
| Serialization | `serialization.ts` | safe JSON/string conversion helpers for editor-visible values |

## CONVENTIONS
- Keep helpers deterministic and side-effect free; pages and components should be able to call them during render.
- Resource ref syntax stays centralized here so agents, schemas, MCP configs, capabilities, and workflows do not invent local parsers.
- Validation helpers return structured issues for editors to render; do not throw for ordinary draft mistakes.
- Serialization helpers must preserve backend-compatible JSON values and avoid silently widening manifest shapes.

## ANTI-PATTERNS
- Do not import React, hooks, route modules, API helpers, or toast/navigation code.
- Do not create feature-specific display labels here when a caller can format them locally.
- Do not add compatibility parsers for retired global authoring ids.

## VALIDATION
```bash
cd frontend
pnpm test:run src/lib/platform-authoring/common/resource-ref.test.ts
```
