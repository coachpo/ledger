# FRONTEND ORCHESTRATION PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`. This file covers the orchestration route family only.

## OVERVIEW
`src/pages/orchestration/` owns the orchestration workspace routes for the landing page, role inventory/editor, and character inventory/editor. These routes stay under the main `Layout` shell and are reachable from the sidebar.

## STRUCTURE
```text
src/pages/orchestration/
├── index.tsx              # orchestration landing page
├── roles/
│   ├── list.tsx           # role inventory, delete flow, and create entry point
│   └── editor.tsx         # role create/edit form
└── characters/
    ├── list.tsx           # character inventory, delete flow, and create entry point
    └── editor.tsx         # character create/edit form
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Workspace landing | `index.tsx` | entry page for orchestration roles and characters |
| Role list | `roles/list.tsx` | inventory cards, delete flow, navigation to create/edit |
| Role editor | `roles/editor.tsx` | role create/update form with immutable key on edit |
| Character list | `characters/list.tsx` | inventory cards, role labels, delete flow, navigation to create/edit |
| Character editor | `characters/editor.tsx` | character create/update form with role selection and immutable handle on edit |
| Data hooks | `../../hooks/use-orchestration.ts` | list/detail queries, create/update/delete mutations, mention catalog invalidation |
| Shared schemas | `../../components/shared/form-schemas.ts` | Zod schemas for role and character create/update forms |

## CONVENTIONS
- Keep this folder scoped to orchestration routes only.
- Roles and characters each have their own list and editor routes, and the landing page is just a navigator between them.
- Use `src/hooks/use-orchestration.ts` for queries and mutations, not direct API calls from page components.
- Use the orchestration form schemas from `src/components/shared/form-schemas.ts` for role and character create/update validation.
- Role keys and character handles are immutable after creation; the page copy and disabled states should reflect that.
- Character editing resolves role selection from the current role catalog and falls back to role keys only when needed.
- Route transitions and toasts belong here, while cache policy and request details stay in hooks.

## ANTI-PATTERNS
- Do not add child docs for `roles/` or `characters/` yet.
- Do not move orchestration pages into `src/components/`.
- Do not treat orchestration as a generic UI concern or mix it into `ui/`.
- Do not call `fetch` directly from these pages.
- Do not duplicate orchestration request logic in the page components when hooks already expose it.
- Do not change the route-family ownership, main `Layout` shell, or sidebar discoverability rules here.

## NOTES
- The orchestration index is a lightweight entry route, not a separate shell.
- Role/character list pages reuse the portfolio `ConfirmDeleteDialog` instead of introducing orchestration-only delete chrome.
- `use-orchestration.test.ts` codifies that write mutations invalidate orchestration collection queries.
