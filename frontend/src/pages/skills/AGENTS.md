# FRONTEND SKILLS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/skills/` contains the routed skill inventory and skill editor. These pages support activation after creation, archive from the list, and one tool definition per line in the editor.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Skill inventory | `list.tsx` | list query, edit, archive, and tool-definition count |
| Skill editor | `editor.tsx` | create/update, activation, and newline-delimited tool ids |
| Skill hooks | `../../hooks/use-skills.ts` | list/detail CRUD, activation, and archive |
| Shared platform helpers | `../platform-resource-shared.tsx` | badges, key sorting, and line-list parsing |
| Skill types | `../../lib/types/skill.ts` | create/update payloads and tool-definition schema |

## CONVENTIONS
- `toolDefinitions` are edited as plain lines, one tool id per line.
- `key` is normalized to lowercase in the editor before submit.
- New skills can be created in draft form, then activated from the edit screen once the record exists.
- `list.tsx` stays focused on inventory actions and summaries, not editing.
- Hooks own cache invalidation, while the page owns toasts and redirect flow after save.

## ANTI-PATTERNS
- Do not store tool definitions in a comma-separated or JSON format.
- Do not move activation into the list page.
- Do not bypass the hook layer for CRUD or archive requests.
- Do not allow empty tool-definition lists to submit.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```
