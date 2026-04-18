# STUDIO PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/studio/` owns the v2 Studio workspace: catalog landing, managed editor routes for agent specs, workflow specs, personas, and capabilities, plus runtime run detail.

## STRUCTURE
```text
src/pages/studio/
├── index.tsx                 # Studio landing page and entry points
├── agents/                   # agent spec list/editor routes and tests
├── workflows/                # workflow spec list/editor routes
├── personas/                 # persona profile list/editor-style inspection routes
├── capabilities/             # capability registry list/editor routes
├── runs/
│   └── detail.tsx            # runtime run detail route
├── shared.tsx                # shared Studio UI helpers
└── shared-utils.ts           # key/label/status helpers for Studio pages
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Studio landing | `index.tsx` | entry cards for agents, workflows, personas, capabilities, and run detail |
| Agent spec routes | `agents/list.tsx`, `agents/editor.tsx` | managed-vs-seeded visibility, editor lifecycle actions |
| Workflow routes | `workflows/list.tsx`, `workflows/editor.tsx` | workflow catalog, drafts, activate/deprecate/archive flow |
| Persona routes | `personas/list.tsx`, `personas/editor.tsx` | managed persona editing with seeded/imported rows remaining read-only |
| Capability routes | `capabilities/list.tsx`, `capabilities/editor.tsx` | capability registry list/detail and managed updates |
| Run detail | `runs/detail.tsx` | runtime output, resolved personas, artifacts, approvals, and trace widgets |
| Hook wiring | `../../hooks/use-studio.ts`, `../../hooks/use-runtime.ts` | Studio catalog queries plus runtime inspection reads |
| API/types | `../../lib/api/studio.ts`, `../../lib/api/workflow-specs.ts`, `../../lib/types/studio.ts`, `../../lib/types/runtime.ts` | v2 request helpers and wire contracts |

## CONVENTIONS
- Studio routes stay thin and delegate network and cache policy to `use-studio.ts` and `use-runtime.ts`.
- `index.tsx` is a hub, not a dashboard with hidden logic; keep route ownership explicit.
- Managed rows stay editable, while seeded or imported rows remain inspection-only when the underlying API marks them that way.
- Route params use stable ids or keys from `src/routes.ts`; keep path handling inside the page layer, not generic components.
- List pages own table-level filters, toasts, and navigation. Editor pages own submit/cancel transitions.
- Run detail is the place for final output, resolved persona/capability context, artifacts, approvals, and trace inspection.

## ANTI-PATTERNS
- Do not hard-code `/api/v2` paths inside pages.
- Do not bypass `use-studio.ts` or `use-runtime.ts` for catalog reads or run-detail data.
- Do not move Studio route logic into generic component folders just because the pages reuse cards or tables.
- Do not treat seeded/imported persona projections as fully editable managed resources.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```

## NOTES
- The Studio landing page is intentionally small and points users to dedicated route families.
- `runs/detail.tsx` is the routed inspection surface for a single runtime run, not a general-purpose shared component.
- Studio pages lean on shared helpers in `shared.tsx` and `shared-utils.ts` to keep list/editor screens consistent without creating a separate feature component tree.
