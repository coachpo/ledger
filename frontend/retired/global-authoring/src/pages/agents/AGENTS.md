# FRONTEND AGENTS PAGES GUIDE

> Retired global-authoring guide. The live app does not route these pages; package-first Workflow Packages own current agent authoring.

## OVERVIEW
`src/pages/agents/` was the retired routed agent inventory and editor. These archived pages handled duplicate, archive, and run-launch flows before package-local agents moved under Workflow Packages.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Agent inventory | `list.tsx` | list query, duplicate, edit, archive, and output schema/capability/MCP summaries |
| Agent editor | `editor.tsx` | create/update, saved model-connection selector, duplicate-from route, archive, and run launch |
| Agent hooks | `../../hooks/use-agents.ts` | list/detail CRUD, archive, and run creation |
| Shared platform helpers | `../platform-resource-shared.tsx` | versioned refs, JSON helpers, badges, and key sorting |
| Agent types | `../../lib/types/agent.ts` | create/update payloads, refs, and run request shape |

## CONVENTIONS
- `list.tsx` stays read-only except for navigation and archive actions.
- `editor.tsx` owns the duplicate-from query param, loads the source agent when cloning, and resets the key for new drafts.
- Agents require a saved model connection; active connections are selectable for new saves while an archived current connection can render as a disabled edit-mode selection.
- Output schema, capability, and MCP bindings stay in newline-delimited versioned refs so the page can parse them with the shared platform helpers.
- Run launch starts from the editor only, after the agent has an id.
- Hooks own cache invalidation, while the page owns toasts, navigation, and draft state.

## ANTI-PATTERNS
- Do not move duplicate or archive behavior into shared UI components.
- Do not bypass the run hook by calling the API from the page.
- Do not split versioned ref parsing away from `platform-resource-shared.tsx`.
- Do not allow new agent drafts to carry over the source key from duplication.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```
