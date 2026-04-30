# FRONTEND CAPABILITIES PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/capabilities/` contains the routed capability inventory and capability editor. These pages support activation after creation, archive from the list, and one tool grant per line in the editor.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Capability inventory | `list.tsx` | list query, edit, archive, and tool-grant count |
| Capability editor | `editor.tsx` | create/update, activation, and newline-delimited tool ids |
| Capability hooks | `../../hooks/use-capabilities.ts` | list/detail CRUD, activation, and archive |
| Shared platform helpers | `../platform-resource-shared.tsx` | badges, key sorting, and line-list parsing |
| Capability types | `../../lib/types/capability.ts` | create/update payloads and tool-grant schema |

## CONVENTIONS
- `toolGrants` are edited as plain lines, one tool id per line.
- `key` is normalized to lowercase in the editor before submit.
- New capabilities can be created in draft form, then activated from the edit screen once the record exists.
- `list.tsx` stays focused on inventory actions and summaries, not editing.
- Hooks own cache invalidation, while the page owns toasts and redirect flow after save.

## ANTI-PATTERNS
- Do not store tool grants in a comma-separated or JSON format.
- Do not move activation into the list page.
- Do not bypass the hook layer for CRUD or archive requests.
- Do not allow empty tool-grant lists to submit.
- Do not create independent `/skills*` pages, aliases, or redirects.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```
