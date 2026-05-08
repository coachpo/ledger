# FRONTEND MCP SERVERS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/mcp-servers/` contains the routed MCP server inventory and editor for `/mcp-servers`, `/mcp-servers/new`, and `/mcp-servers/:serverId/edit`. The page family covers archive, activate, and connection-test flows. Transport-specific command and URL rules stay in the editor, while MCP security and runtime dispatch stay on the backend.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| MCP server inventory | `list.tsx` | list query, edit, archive, and transport summary |
| MCP server editor | `editor.tsx` | create/update, activate, test connection, auth JSON, transport rules |
| MCP server hooks | `../../hooks/use-mcp-servers.ts` | list/detail CRUD, activate, archive, and connection test |
| Shared platform helpers | `../platform-resource-shared.tsx` | badges, JSON helpers, and key sorting |
| MCP server types | `../../lib/types/mcp-server.ts` | transport, auth, command, URL, and activation payloads |

## CONVENTIONS
- `stdio` servers require a command, while `http-sse` servers require a URL.
- Auth is edited as JSON and parsed through the shared JSON helper.
- `key` is normalized to lowercase before submit.
- `list.tsx` only handles inventory actions and summaries, not connection testing.
- Hooks own cache invalidation and connection-test requests, while the page owns toasts and inline feedback.
- Keep version, activation, and archive wording aligned with the platform resource pages.
- Treat test-connection feedback as local UI state until the hook response updates server-backed fields.

## ROUTE NOTES
- `/mcp-servers` is the inventory and action surface.
- `/mcp-servers/new` creates a draft server config.
- `/mcp-servers/:serverId/edit` edits, activates, archives, and tests an existing config.
- Runtime tool snapshots, exact MCP version pins, redaction, and truncation are backend contracts. The page should display returned metadata without recreating those rules.

## ANTI-PATTERNS
- Do not let a `stdio` draft submit without a command.
- Do not let an `http-sse` draft submit without a URL.
- Do not store auth as freeform text outside JSON handling.
- Do not bypass the hook layer for activate, archive, or test-connection calls.
- Do not add browser-side MCP client execution, secret handling, snapshot hashing, or output redaction here.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```
