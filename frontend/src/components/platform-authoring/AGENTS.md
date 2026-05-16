# FRONTEND PLATFORM AUTHORING COMPONENTS GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/components/AGENTS.md`.

## OVERVIEW
`src/components/platform-authoring/` contains editor widgets for package-local platform authoring: schema composition, generated schema-driven forms, workflow wiring, package resource selectors, and structured value inspection. Components are UI-only and are driven by `src/lib/platform-authoring/**` types/helpers.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

## STRUCTURE
```text
platform-authoring/
├── generated-form/   # schema-driven value-entry form renderer
├── schema-composer/  # JSON Schema subset builder UI
├── workflow-builder/ # workflow step/wire-binding wizard UI
├── refs/             # single/multi package-resource selectors
└── inspectors/       # read-only structured output displays
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Generated input forms | `generated-form/schema-form.tsx` | schema IR + value-entry rendering and validation display |
| Schema builder UI | `schema-composer/schema-composer.tsx` | object/array/scalar/discriminated-union editor surface |
| Workflow builder UI | `workflow-builder/workflow-builder-wizard.tsx` | step composition, slots, wire bindings, validation feedback |
| Resource selectors | `refs/*.tsx` | package-local agent/capability/MCP/output-schema ref inputs |
| Structured previews | `inspectors/structured-value-inspector.tsx` | read-only nested value display |

## CONVENTIONS
- Components receive drafts, IR nodes, refs, and callbacks from pages; they do not fetch or mutate server state.
- Keep parsing, serialization, and validation in `src/lib/platform-authoring/**`; components render the result and collect user edits.
- `generated-form/` owns schema-driven value editing, not generic form primitives.
- `schema-composer/` owns authoring for the supported schema subset only.
- `workflow-builder/` owns workflow wiring UI and delegates path/slot validation to lib helpers.

## ANTI-PATTERNS
- Do not call API helpers, hooks, navigation, or toasts from this directory.
- Do not duplicate schema/value/workflow codecs in components.
- Do not move app-wide shadcn primitives into this feature folder.
- Do not make these widgets depend on specific route ids when props can carry the required data.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```
