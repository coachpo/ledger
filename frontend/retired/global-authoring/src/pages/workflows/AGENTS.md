# FRONTEND WORKFLOWS PAGES GUIDE

> Retired global-authoring guide. The live app does not route these pages; package-private workflow graphs own current workflow authoring.

## OVERVIEW
`src/pages/workflows/` was the retired workflow inventory, detail, launch, and editor route family for `/workflows`, `/workflows/new`, `/workflows/:workflowId`, `/workflows/:workflowId/edit`, and `/workflows/:workflowId/run`.

The application is under active development and has no users at the moment; future upgrade, migration, and compatibility design must account for that and should not preserve speculative legacy paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Workflow inventory | `list.tsx` | list query plus detail, edit, and run-now entry points |
| Workflow detail | `detail.tsx` | workflow metadata and workflow-scoped run history |
| Workflow launch | `launch.tsx` | version selection, generated parameters form, and queued launch submit |
| Workflow editor | `editor.tsx` | create/update and editor review only |
| Workflow draft helpers | `shared.ts` | section model, draft conversion, validation, payload building |
| Workflow hooks | `../../hooks/use-workflows.ts` | list/detail CRUD, launch metadata, version list, and launch creation |
| Agent lookup | `../../hooks/use-agents.ts` | agent catalog used by the editor |
| Run route | `../runs/detail.tsx` | launched runs open at `/runs/:runId` |

## CONVENTIONS
- `shared.ts` owns the draft shape, section list, validation rules, and payload conversion.
- The editor keeps the wizard sections explicit instead of flattening everything into one form.
- Archived run launch lived on `/workflows/:workflowId/run`, posted the strict `{version, parameters}` envelope through the launch hook, and then routed to the created run detail view.
- Review is an editor step, not a run-launch surface.
- Agent selection and wiring stay versioned, with the editor loading agent catalog data to build the draft.
- Hooks own cache invalidation and workflow launch creation, while pages own route state, review state, launch form state, and navigation.

## ANTI-PATTERNS
- Do not duplicate draft or payload helpers inside the editor component.
- Do not collapse the wizard into a single unsectioned form.
- Do not add launch controls back to the workflow editor or its `#review` state.
- Do not bypass the workflow launch hook when launching a run.
- Do not navigate run launches to anything other than the run detail route.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```
