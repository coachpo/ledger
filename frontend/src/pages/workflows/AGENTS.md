# FRONTEND WORKFLOWS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/workflows/` contains the routed workflow inventory and workflow editor. The editor is sectioned into input, steps, output, and review, then launches runs that navigate to `/runs/:runId`.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Workflow inventory | `list.tsx` | list query, edit, and run-now entry points |
| Workflow editor | `editor.tsx` | create/update, review, and run launch |
| Workflow draft helpers | `shared.ts` | section model, draft conversion, validation, payload building |
| Workflow hooks | `../../hooks/use-workflows.ts` | list/detail CRUD and run creation |
| Agent lookup | `../../hooks/use-agents.ts` | agent catalog used by the editor |
| Run route | `../runs/detail.tsx` | launched runs open at `/runs/:runId` |

## CONVENTIONS
- `shared.ts` owns the draft shape, section list, validation rules, and payload conversion.
- The editor keeps the wizard sections explicit instead of flattening everything into one form.
- Run launch uses the workflow hook and then routes to the created run detail view.
- Review is an editor step, not a separate routed screen.
- Agent selection and wiring stay versioned, with the editor loading agent catalog data to build the draft.
- Hooks own cache invalidation and run creation, while the page owns wizard state, review state, and navigation.

## ANTI-PATTERNS
- Do not duplicate draft or payload helpers inside the editor component.
- Do not collapse the wizard into a single unsectioned form.
- Do not bypass the workflow hook when launching a run.
- Do not navigate run launches to anything other than the run detail route.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```
