# FRONTEND CAPABILITIES PAGES GUIDE

> Retired global-authoring guide. The live app does not route these pages; package-local capability profiles own current tool grants.

## OVERVIEW
`src/pages/capabilities/` was the retired routed capability inventory and editor. These archived pages supported activation, archive, and strict catalog selection before capability profiles moved inside Workflow Packages.

The application is under active development and has no users at the moment; future upgrade, migration, and compatibility design must account for that and should not preserve speculative legacy paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Capability inventory | `list.tsx` | list query, edit, archive, and resolved tool count |
| Capability editor | `editor.tsx` | create/update, activation, and catalog-backed `toolKeys` selection |
| Capability hooks | `../../hooks/use-capabilities.ts` | list/detail CRUD, catalog tools, activation, and archive |
| Shared platform helpers | `../platform-resource-shared.tsx` | badges, key sorting, and JSON preview helpers |
| Capability types | `../../lib/types/capability.ts` | create/update payloads, `toolKeys`, and read-only `tools` metadata |

## CONVENTIONS
- `toolKeys` are selected from the strict server catalog picker, not typed as free-text lines.
- Reads may include read-only resolved `tools` metadata for display counts and labels.
- `key` is normalized to lowercase in the editor before submit.
- New capabilities can be created in draft form, then activated from the edit screen once the record exists.
- `list.tsx` stays focused on inventory actions and summaries, not editing.
- Hooks own cache invalidation, while the page owns toasts and redirect flow after save.

## ANTI-PATTERNS
- Do not reintroduce `toolGrants`, comma-separated tool lists, JSON text areas, or free-text tool-key entry.
- Do not move activation into the list page.
- Do not bypass the hook layer for CRUD, catalog reads, or archive requests.
- Do not allow empty `toolKeys` selections to submit.
- Do not create independent `/skills*` pages, aliases, or redirects.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```
