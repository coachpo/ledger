# FRONTEND PLATFORM AUTHORING WORKFLOW PACKAGES LIB GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, `/frontend/src/lib/AGENTS.md`, and `/frontend/src/lib/platform-authoring/AGENTS.md`.

## OVERVIEW
`workflow-packages/` owns browser-side Workflow Package manifest parsing, serialization, resource assembly, runtime-input registry wiring, package secret binding shapes, and private MCP transport normalization for package artifacts.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Package manifest helpers | `manifest.ts` | parse/serialize/assemble package-local resources and private MCP config drafts |
| Coverage | `manifest.test.ts` | round-trips, YAML restrictions, private MCP fields, and package artifact shape |

## CONVENTIONS
- Package manifests are the only executable workflow authoring root in the browser.
- Private MCP `env`, `headers`, and `query` values are secret-bearing authoring/runtime config; browser-visible reads and exports must omit them.
- Runtime-input registry and package secret binding shapes stay package-scoped; do not move them into global route helpers.
- Preserve package-local refs as refs, not raw database ids.

## ANTI-PATTERNS
- Do not reintroduce standalone agents, capabilities, MCP servers, output schemas, or workflows from this layer.
- Do not add network calls or TanStack Query state here; API helpers live in `src/lib/api/workflow-packages.ts`.
- Do not loosen YAML restrictions without updating backend compiler/parser tests.

## VALIDATION
```bash
cd frontend
pnpm test:run src/lib/platform-authoring/workflow-packages/manifest.test.ts
```

## NOTES
- Keep this guide focused on browser-side package artifact shaping; route UX rules live in `src/pages/workflow-packages/AGENTS.md`.
